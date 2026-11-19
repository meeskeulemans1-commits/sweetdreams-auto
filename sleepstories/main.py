"""Dagelijkse run: verhaal -> stem -> beeld -> video -> upload."""
import argparse, datetime as dt, json, os, shutil, subprocess, sys
from . import story as S, tts, ambient, footage, render, thumb

HIST = "history.json"


def load_hist():
    if os.path.exists(HIST): return json.load(open(HIST))
    return {"videos": [], "clip_ids": []}


def fmt(t):
    t = int(t); return f"{t//60}:{t%60:02d}"


def description(story, starts, intro_len, total_len):
    lines = ["0:00 Intro"] + [f"{fmt(s + intro_len)} {c['title']}" for s, c in zip(starts, story["chapters"])]
    return (f"{story['summary']}\n\nLength: about {int(round(total_len/60))} minutes. You are welcome to fall asleep at any point. "
            f"There is no need to stay awake until the end.\n\nChapters:\n" + "\n".join(lines) +
            "\n\nTips for a good night: turn the screen brightness down, set the volume low, and put on a sleep timer if you like."
            "\n\nIf this story helped you relax, please like and subscribe for a new calm sleep story every day. Sleep well."
            "\n\n#sleepstory #bedtimestory #relaxing #sleep #calm")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="alles maken maar niet uploaden")
    ap.add_argument("--story-file", help="gebruik dit verhaal (json) i.p.v. Claude")
    ap.add_argument("--work", default="work")
    ap.add_argument("--mode", default=os.environ.get("PUBLISH_MODE", "scheduled"))
    ap.add_argument("--force", action="store_true", help="ook als er vandaag al een video is")
    a = ap.parse_args()

    hist = load_hist(); today = dt.date.today().isoformat()
    if not a.force and not a.dry_run and any(v["date"] == today for v in hist["videos"]):
        print("Vandaag is er al een video gemaakt; stop."); return
    work = a.work; shutil.rmtree(work, ignore_errors=True); os.makedirs(work)

    if a.story_file: story = json.load(open(a.story_file))
    else: story = S.write_story([v["title"] for v in hist["videos"]], [v.get("place", "") for v in hist["videos"][-20:]])
    json.dump(story, open(os.path.join(work, "story.json"), "w"), indent=1)
    title = story["title"]
    full_title = f"{title} | {({'45': '45 Minute', '60': '1 Hour'}.get(os.environ.get('LONG_MINUTES', '0'), 'Calm'))} Sleep Story for Deep Sleep (Soft Voice, Gentle Music)"
    print("[main] titel:", full_title, flush=True)

    tm = tts.synthesize(story, work)
    amb = ambient.make(os.path.join(work, "amb.wav"), tm["total"] + 24.0)
    N = len(story["chapters"]); B = tm["bounds"]; TOTAL = tm["total"] + 24.0
    durs = [(B[i + 1] if i < N - 1 else TOTAL) - B[i] + 2 for i in range(N)]
    clips = footage.gather(story, os.environ["PEXELS_API_KEY"], durs, hist["clip_ids"], work)

    main_v = os.path.join(work, "story_only.mp4")
    render.render_all(story, tm, clips, tm["wav"], amb, work, main_v, title)
    final = os.path.join(work, "final.mp4")
    render.prepend_intro(main_v, "assets/intro.mp4", final, work)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]))
    intro_len = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "assets/intro.mp4"]))
    print(f"[main] eindvideo {dur/60:.1f} min, {os.path.getsize(final)/1e6:.0f} MB", flush=True)
    if not float(os.environ.get("MIN_MINUTES", 15)) * 60 <= dur <= float(os.environ.get("MAX_MINUTES", 35)) * 60: sys.exit(f"Lengte {dur/60:.1f} min ligt buiten bereik; niet uploaden")
    thumbp = thumb.make(os.path.join(work, "thumbnail.jpg"), [[(c[0], c[1], c[2]) for c in ch] for ch in clips], title)
    desc = description(story, tm["starts"], intro_len, dur)
    tags = story["tags"]
    open(os.path.join(work, "description.txt"), "w").write(full_title + "\n\n" + desc)

    if a.dry_run:
        print("[main] dry-run: niet geupload"); return
    from . import upload
    vid, real = upload.upload(final, thumbp, full_title, desc, tags, a.mode)
    hist["videos"].append({"date": today, "title": title, "video_id": vid, "place": story.get("place", ""),
                           "privacy": real.get("privacyStatus"), "publishAt": real.get("publishAt")})
    hist["clip_ids"] = (hist["clip_ids"] + [c[3] for ch in clips for c in ch])[-1500:]
    json.dump(hist, open(HIST, "w"), indent=1)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
