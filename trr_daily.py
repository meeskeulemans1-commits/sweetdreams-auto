"""TRR: plant video's uit GitHub-releases in op YouTube (private + publishAt).
Elke release bevat per video: <id>.mp4 / <id>_16x9.mp4, <id>.jpg en <id>.json (zie schedule/items).
Gebruik: python trr_daily.py [--lookahead 2] [--max 5] [--dry-run]
Secrets (env): YT_CLIENT_ID, YT_CLIENT_SECRET, TRR_REFRESH_TOKEN. GH_TOKEN voor gh."""
import argparse, datetime as dt, glob, json, os, subprocess, sys, tempfile
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

DONE = "trr_uploaded.json"; NL = ZoneInfo("Europe/Amsterdam")

def sh(*a): return subprocess.run(a, check=True, capture_output=True, text=True).stdout

def service():
    """Probeert eerst het TRR-OAuth-client, dan de standaard YT-client (het refresh token hoort bij een van beide)."""
    from google.auth.transport.requests import Request
    pairs = [(os.environ.get("TRR_CLIENT_ID"), os.environ.get("TRR_CLIENT_SECRET")), (os.environ.get("YT_CLIENT_ID"), os.environ.get("YT_CLIENT_SECRET"))]
    last = None
    for cid, sec in pairs:
        if not cid or not sec: continue
        c = Credentials(None, refresh_token=os.environ["TRR_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token",
                        client_id=cid, client_secret=sec, scopes=["https://www.googleapis.com/auth/youtube.upload"])
        try: c.refresh(Request())
        except Exception as e: last = e; print("OAuth-client", cid[:12], "werkt niet voor dit token:", str(e)[:120]); continue
        print("OAuth-client gebruikt:", cid[:12]); return build("youtube", "v3", credentials=c, cache_discovery=False)
    raise SystemExit(f"Geen werkende OAuth-combinatie voor TRR_REFRESH_TOKEN: {last}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--lookahead", type=int, default=2); ap.add_argument("--max", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--today", default=""); a = ap.parse_args()
    done = json.load(open(DONE)) if os.path.exists(DONE) else {}
    now = dt.datetime.now(NL); horizon = now.date() + dt.timedelta(days=a.lookahead)
    work = tempfile.mkdtemp(); items = []
    seen = set(); ov = {}
    for rel in json.loads(sh("gh", "release", "list", "--json", "tagName,isDraft", "--limit", "100")):
        tag = rel["tagName"]
        if rel.get("isDraft") or tag in seen or not tag.lower().startswith("trr"): continue  # alleen TRR-releases (tag begint met trr)
        seen.add(tag); d = os.path.join(work, tag); os.makedirs(d, exist_ok=True)
        subprocess.run(["gh", "release", "download", tag, "-p", "*.json", "-D", d], capture_output=True)
        for p in glob.glob(d + "/*.json"):
            try: it = json.load(open(p))
            except Exception: continue
            if isinstance(it, dict) and "overrides" in it:  # nieuwste release wint: {"overrides": {id: {"publish_date":..., "publish_time":...}}}
                for k, v in it["overrides"].items(): ov.setdefault(k, v)
            elif "publish_date" in it and "video" in it: it["_tag"] = tag; it["_dir"] = d; items.append(it)
    uniq = {}
    for it in items: uniq.setdefault(it["id"], it)  # releases staan nieuwste eerst: de nieuwste versie van een id wint
    items = list(uniq.values())
    for it in items:
        if it["id"] in ov: it.update({k: v for k, v in ov[it["id"]].items() if k in ("publish_date", "publish_time")}); print("OVERRIDE:", it["id"], ov[it["id"]])
    items.sort(key=lambda i: (i["publish_date"], i.get("publish_time", "00:00")))
    if a.today:  # extra Shorts vandaag: pak de laatste nog niet geplande Shorts uit de voorraad en zet ze op vandaag
        tijden = [t.strip() for t in a.today.split(",") if t.strip()]
        pool = [i for i in items if i["id"] not in done and i["title"].rstrip().endswith("#shorts")]
        for it, t in zip(reversed(pool[-len(tijden):]), reversed(tijden)):
            it["publish_date"] = now.date().isoformat(); it["publish_time"] = t; print("VANDAAG:", it["id"], t)
        items.sort(key=lambda i: (i["publish_date"], i.get("publish_time", "00:00")))
    todo = []
    for it in items:
        when = dt.datetime.fromisoformat(f"{it['publish_date']}T{it.get('publish_time', '18:00')}:00").replace(tzinfo=NL)
        if it["id"] in done or when.date() > horizon: continue
        if when <= now + dt.timedelta(minutes=20): print("OVERGESLAGEN (tijdstip voorbij):", it["id"], when); continue
        todo.append((it, when))
    print(f"{len(todo)} te plannen, max {a.max} deze run"); yt = None if a.dry_run else service()
    for it, when in todo[:a.max]:
        pub = when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print("->", it["id"], it["title"], "publishAt", pub, "(NL", when.strftime("%d-%m %H:%M") + ")")
        if a.dry_run: continue
        for f in (it["video"], it.get("thumbnail")):
            if f: subprocess.run(["gh", "release", "download", it["_tag"], "-p", f, "-D", it["_dir"]], check=True)
        body = {"snippet": {"title": it["title"][:100], "description": it["description"][:4900], "tags": it.get("tags", []), "categoryId": "27"},
                "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": False}}
        r = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(os.path.join(it["_dir"], it["video"]), chunksize=-1, resumable=True)).execute()
        vid = r["id"]; print("   video-id", vid)
        th = os.path.join(it["_dir"], it.get("thumbnail", "")) if it.get("thumbnail") else None
        if th and os.path.exists(th):
            try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th)).execute()
            except Exception as e: print("   thumbnail mislukt (kanaal nog niet geverifieerd?):", str(e)[:150])
        done[it["id"]] = {"video_id": vid, "publishAt": pub, "title": it["title"]}
        json.dump(done, open(DONE, "w"), indent=1, ensure_ascii=False)
    left = len(todo) - a.max
    if left > 0: print(f"{left} blijven liggen voor de volgende run (YouTube-quota: ~6 uploads/dag per project)")

if __name__ == "__main__": main()
