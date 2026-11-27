"""Kanaalfabriek: een uploader voor alle kanalen.

Gebruik: python -m factory.upload <kanaal> [--dry-run] [--max N] [--lookahead DAGEN]

Bronnen voor video's (per item een .json + video + thumbnail):
  1. branch `media`, map <kanaal>/        (nieuwe aanpak: bestanden klaarzetten met git)
  2. GitHub-releases met tag die begint met channels.json -> release_prefix (oude aanpak, alleen als ingesteld)
Elk item: id, video, thumbnail, title, description, tags, publish_date, publish_time of slot.
Staat per kanaal: state/<kanaal>.json  {id: {video_id, publishAt, title}}.
Veiligheid: dedupe op id en op titel, nooit dezelfde video twee keer, stopt netjes bij uploadlimiet,
gemiste tijdstippen worden automatisch naar de eerstvolgende dag verschoven.
"""
import argparse, datetime as dt, glob, json, os, re, shutil, subprocess, sys, tempfile
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(*a, check=True):
    return subprocess.run(a, check=check, capture_output=True, text=True)


def norm(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def service(cfg):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    last = None
    for cid_env, sec_env in cfg["clients"]:
        cid, sec = os.environ.get(cid_env), os.environ.get(sec_env)
        tok = os.environ.get(cfg["refresh_env"])
        if not (cid and sec and tok):
            continue
        c = Credentials(None, refresh_token=tok, token_uri="https://oauth2.googleapis.com/token",
                        client_id=cid, client_secret=sec, scopes=["https://www.googleapis.com/auth/youtube.upload"])
        try:
            c.refresh(Request())
        except Exception as e:
            last = e
            print(f"OAuth-client {cid[:12]} werkt niet voor {cfg['refresh_env']}: {str(e)[:120]}")
            continue
        print("OAuth-client gebruikt:", cid[:12])
        return build("youtube", "v3", credentials=c, cache_discovery=False)
    raise SystemExit(f"Geen werkende OAuth-combinatie voor {cfg['refresh_env']}: {last}")


def collect(ch, cfg, work):
    """Geeft lijst items terug; elk met _dir (map waarin de bestanden staan) en _src."""
    items = []
    # 1. media-branch
    md = os.environ.get("FACTORY_MEDIA_DIR") or os.path.join(work, "media")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and not os.environ.get("FACTORY_MEDIA_DIR"):
        url = f"https://x-access-token:{os.environ.get('GH_TOKEN', '')}@github.com/{repo}.git"
        r = sh("git", "clone", "-q", "--depth", "1", "--branch", "media", url, md, check=False)
        if r.returncode != 0:
            print("(geen media-branch of niet te klonen:", r.stderr.strip()[:120].replace(os.environ.get("GH_TOKEN", "x"), "***"), ")")
    for p in glob.glob(os.path.join(md, ch, "*.json")):
        try:
            it = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if isinstance(it, dict) and "video" in it:
            it.setdefault("id", os.path.splitext(os.path.basename(p))[0]); it["_dir"] = os.path.dirname(p); it["_src"] = "media"
            items.append(it)
    # 2. releases (oud)
    pre = cfg.get("release_prefix")
    if pre:
        ov = {}
        r = sh("gh", "release", "list", "--json", "tagName,isDraft", "--limit", "100", check=False)
        rels = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
        if r.returncode != 0:
            print("(releases niet op te halen:", r.stderr.strip()[:120], ")")
        for rel in rels:
            tag = rel["tagName"]
            if rel.get("isDraft") or not tag.lower().startswith(pre):
                continue
            d = os.path.join(work, "rel", tag); os.makedirs(d, exist_ok=True)
            sh("gh", "release", "download", tag, "-p", "*.json", "-D", d, check=False)
            for p in glob.glob(d + "/*.json"):
                try:
                    it = json.load(open(p, encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(it, dict) and "overrides" in it:
                    for k, v in it["overrides"].items():
                        ov.setdefault(k, v)
                elif isinstance(it, dict) and "video" in it and "publish_date" in it:
                    it.setdefault("id", os.path.splitext(os.path.basename(p))[0])
                    it["_dir"] = d; it["_tag"] = tag; it["_src"] = "release"
                    items.append(it)
        for it in items:
            if it["id"] in ov:
                it.update({k: v for k, v in ov[it["id"]].items() if k in ("publish_date", "publish_time")})
    uniq = {}
    for it in items:                      # media wint van releases, daarna de eerste (nieuwste)
        uniq.setdefault(it["id"], it)
    return list(uniq.values())


def when_of(it, cfg, now, tz):
    t = it.get("publish_time") or cfg["slots"].get(it.get("slot", "short"), "18:00")
    when = dt.datetime.fromisoformat(f"{it['publish_date']}T{t}:00").replace(tzinfo=tz)
    shifted = 0
    while when <= now + dt.timedelta(minutes=20) and shifted < 14:
        when += dt.timedelta(days=1); shifted += 1
    return when, shifted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=None); ap.add_argument("--lookahead", type=int, default=None)
    a = ap.parse_args()
    cfgs = json.load(open(os.path.join(ROOT, "channels.json")))
    cfg = cfgs[a.channel]; tz = ZoneInfo(cfg["tz"])
    mx = a.max or cfg["max_per_run"]; look = a.lookahead if a.lookahead is not None else cfg["lookahead_days"]
    sp = os.path.join(ROOT, "state", f"{a.channel}.json")
    done = json.load(open(sp)) if os.path.exists(sp) else {}
    done_titles = {norm(v.get("title", "")) for v in done.values()}
    now = dt.datetime.now(tz); horizon = now.date() + dt.timedelta(days=look)
    work = tempfile.mkdtemp()
    items = collect(a.channel, cfg, work)
    todo = []
    for it in items:
        if it["id"] in done:
            continue
        if norm(it["title"]) in done_titles:
            print("DUBBELE TITEL, overgeslagen:", it["id"], it["title"]); continue
        when, sh_days = when_of(it, cfg, now, tz)
        if when.date() > horizon:
            continue
        if sh_days:
            print(f"VERSCHOVEN +{sh_days}d (tijd was voorbij): {it['id']} -> {when:%d-%m %H:%M}")
        todo.append((it, when))
    todo.sort(key=lambda x: x[1])
    # nooit twee video's op hetzelfde tijdstip
    taken = {v.get("publishAt") for v in done.values()}
    print(f"[{a.channel}] {len(items)} items gevonden, {len(todo)} te plannen (max {mx} per run)")
    yt = None if a.dry_run else service(cfg)
    errors = 0
    from googleapiclient.http import MediaFileUpload
    for it, when in todo[:mx]:
        pub = when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        while pub in taken:
            when += dt.timedelta(minutes=30); pub = when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print("->", it["id"], "|", it["title"], "| publishAt", pub, f"(lokaal {when:%d-%m %H:%M})")
        if a.dry_run:
            taken.add(pub); continue
        if it["_src"] == "release":
            for f in (it["video"], it.get("thumbnail")):
                if f: sh("gh", "release", "download", it["_tag"], "-p", f, "-D", it["_dir"], "--clobber")
        vpath = os.path.join(it["_dir"], it["video"])
        if not os.path.exists(vpath):
            print("   VIDEO ONTBREEKT:", vpath); errors += 1; continue
        body = {"snippet": {"title": it["title"][:100], "description": it["description"][:4900], "tags": it.get("tags", [])[:30],
                            "categoryId": cfg["category"], "defaultLanguage": cfg["language"], "defaultAudioLanguage": cfg["language"]},
                "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": False, "embeddable": True}}
        try:
            r = yt.videos().insert(part="snippet,status", body=body,
                                   media_body=MediaFileUpload(vpath, chunksize=-1, resumable=True, mimetype="video/mp4")).execute()
        except Exception as e:
            s = str(e)
            if "uploadLimitExceeded" in s or "quotaExceeded" in s:
                print("UPLOADLIMIET/QUOTA bereikt: stoppen, de rest volgt bij de volgende run"); break
            print("UPLOAD MISLUKT:", it["id"], s[:300]); errors += 1; continue
        vid = r["id"]; print("   video-id", vid)
        done[it["id"]] = {"video_id": vid, "publishAt": pub, "title": it["title"]}
        taken.add(pub); done_titles.add(norm(it["title"]))
        os.makedirs(os.path.dirname(sp), exist_ok=True)
        json.dump(done, open(sp, "w"), indent=1, ensure_ascii=False)       # meteen opslaan: nooit dubbel bij een crash
        th = os.path.join(it["_dir"], it["thumbnail"]) if it.get("thumbnail") else None
        if th and os.path.exists(th):
            try:
                yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute()
            except Exception as e:
                print("   thumbnail mislukt:", str(e)[:150])
    left = len(todo) - mx
    if left > 0:
        print(f"{left} blijven liggen voor de volgende run")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a") as f:
            f.write(f"### {a.channel}: {len(todo)} gepland, {errors} fouten\n")
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
