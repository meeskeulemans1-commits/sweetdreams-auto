"""Dagelijkse upload voor Wartime Wrong.

Zoekt in alle GitHub-releases naar items (een .json met publish_date + slot) die op de gevraagde dag
(standaard vandaag, NL-tijd) gepubliceerd moeten worden, uploadt ze naar YouTube en plant ze op vaste tijden.
Welke items al geupload zijn staat in ww_uploaded.json.
"""
import os, sys, json, glob, subprocess, datetime as dt
from zoneinfo import ZoneInfo
from googleapiclient.http import MediaFileUpload
from wartimewrong_upload import service

TZ = ZoneInfo("Europe/Amsterdam")
SLOTS = {"short": 18, "long": 21}     # uur (NL-tijd): Short 18:00 (12:00 US-oost), lange video 21:00 (15:00 US-oost)
STATE = "ww_uploaded.json"


def run(*a, check=True):
    return subprocess.run(a, check=check, capture_output=True, text=True)


def publish_utc(day, slot):
    t = dt.datetime.fromisoformat(day).replace(hour=SLOTS.get(slot, 18), tzinfo=TZ)
    if t <= dt.datetime.now(TZ) + dt.timedelta(minutes=15):
        return None                                   # tijd is al geweest: dan meteen openbaar
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def find_items(day, done):
    items = []
    tags = [r["tagName"] for r in json.loads(run("gh", "release", "list", "--limit", "50", "--json", "tagName").stdout)]
    for tag in tags:
        if tag.lower().startswith("trr"): continue   # TRR-releases horen bij een ander kanaal
        d = f"dl/{tag}"; os.makedirs(d, exist_ok=True)
        run("gh", "release", "download", tag, "-p", "*.json", "-D", d, "--clobber", check=False)
        for f in sorted(glob.glob(d + "/*.json")):
            try:
                meta = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            if meta.get("publish_date") != day or "video" not in meta:
                continue
            key = f"{tag}/{os.path.basename(f)}"
            if key not in done:
                items.append((tag, key, meta, d))
    items.sort(key=lambda x: SLOTS.get(x[2].get("slot"), 18))
    return items


def upload(tag, meta, d, when):
    pats = [meta["video"]] + ([meta["thumbnail"]] if meta.get("thumbnail") else [])
    cmd = ["gh", "release", "download", tag, "-D", d, "--clobber"]
    for p in pats: cmd += ["-p", p]
    run(*cmd)
    video = os.path.join(d, meta["video"])
    status = {"selfDeclaredMadeForKids": False, "embeddable": True}
    if when:
        status["privacyStatus"] = "private"; status["publishAt"] = when
    else:
        status["privacyStatus"] = "public"
    body = {"snippet": {"title": meta["title"][:100], "description": meta["description"][:4900],
                        "tags": meta.get("tags", [])[:30], "categoryId": "27",
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"}, "status": status}
    yt = service()
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(video, chunksize=32 * 1024 * 1024, resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        st, resp = req.next_chunk()
        if st: print(f"[upload] {int(st.progress()*100)}%", flush=True)
    vid = resp["id"]
    print(f"[upload] klaar: https://youtu.be/{vid} publishAt={when or 'nu (openbaar)'}", flush=True)
    th = os.path.join(d, meta["thumbnail"]) if meta.get("thumbnail") else None
    if th and os.path.exists(th):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute()
            print("[upload] thumbnail gezet", flush=True)
        except Exception as e:
            print("[upload] thumbnail mislukt:", str(e)[:200], flush=True)
    return vid


def main():
    day = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or dt.datetime.now(TZ).date().isoformat()
    dry = len(sys.argv) > 2 and sys.argv[2] == "true"
    done = json.load(open(STATE)) if os.path.exists(STATE) else []
    items = find_items(day, done)
    print(f"[daily] datum {day}: {len(items)} item(s) om te uploaden", flush=True)
    for tag, key, meta, d in items:
        when = publish_utc(day, meta.get("slot"))
        print(f"[daily] {key} | {meta.get('slot')} | {meta['title']} | publishAt={when}", flush=True)
        if dry:
            continue
        try:
            upload(tag, meta, d, when)
        except Exception as e:
            print(f"[daily] MISLUKT: {key}: {str(e)[:300]}", flush=True)
            continue
        done.append(key)
        json.dump(done, open(STATE, "w"), indent=1)
    if not items:
        print("[daily] niets te doen vandaag", flush=True)


if __name__ == "__main__":
    main()
