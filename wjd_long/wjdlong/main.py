"""WistJeDatDieren: Top 10-video van 8-10 minuten maken en uploaden."""
import argparse, datetime as dt, glob, json, os, shutil, subprocess, sys
from zoneinfo import ZoneInfo
from . import story as S, tts, footage, render, thumb

HIST = os.environ.get("WJD_HISTORY", "wjd_long_history.json")
QDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "queue")


def next_queued(hist):
    """Volgend script uit de wachtrij (wjd_long/queue/*.txt, op bestandsnaam) dat nog niet is gebruikt."""
    used = {v.get("queue_file") for v in hist["videos"]}
    for f in sorted(glob.glob(os.path.join(QDIR, "*.txt"))):
        if os.path.basename(f) not in used:
            return f
    return None


def fmt(t): t = int(round(t)); return f"{t // 60}:{t % 60:02d}"


def description(st, tl):
    lines = [st["summary"], "", "Wat vind jij de coolste? Laat het weten in de reacties! Like, reageer en abonneer voor elke dag een nieuw dierenweetje.", "", "Hoofdstukken:", "0:00 Intro"]
    for seg in tl["segments"]:
        if seg["name"].startswith("item"):
            r = int(seg["name"][4:]); it = next(i for i in st["items"] if i["rank"] == r)
            lines.append(f"{fmt(seg['start'])} Nummer {r}: {it['name']}")
        elif seg["name"] == "outro": lines.append(f"{fmt(seg['start'])} Tot slot")
    lines += ["", "Beeldmateriaal: Pexels. Stem: computerstem. Scripts worden met AI geschreven en gecontroleerd op feiten.", "", "#dieren #weetjes #top10 #wistjedat"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--mode", default=os.environ.get("PUBLISH_MODE", "scheduled"))
    ap.add_argument("--force", action="store_true"); ap.add_argument("--theme"); ap.add_argument("--story-file")
    a = ap.parse_args()
    hist = json.load(open(HIST)) if os.path.exists(HIST) else {"videos": []}
    today = dt.datetime.now(ZoneInfo("Europe/Amsterdam")).strftime("%Y-%m-%d")
    if not a.force and not a.dry_run and any(v["date"] == today for v in hist["videos"]):
        print("[main] vandaag is al een lange video gemaakt; niets te doen"); return
    qf = None
    if not a.story_file and not a.theme:
        qf = next_queued(hist)
        if qf: a.story_file = qf; print(f"[main] script uit wachtrij: {os.path.basename(qf)}", flush=True)
    work = os.environ.get("WJD_WORK", "work"); shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    clipdir = os.environ.get("WJD_CLIPS") or os.path.join(work, "clips"); os.makedirs(clipdir, exist_ok=True)
    if a.story_file: st = S.parse(open(a.story_file, encoding="utf-8").read()); st.setdefault("theme", os.path.basename(a.story_file) if qf else "test"); st["items"].sort(key=lambda x: -x["rank"])
    else:
        try: st = S.write([v["title"] for v in hist["videos"]] + [v.get("theme", "") for v in hist["videos"]], a.theme)
        except Exception as e:
            print(f"::warning::Wachtrij is leeg en het schrijven met de API mislukte ({str(e)[:120]}). Geen video gemaakt; nieuwe scripts toevoegen aan wjd_long/queue/.", flush=True); return
    print(f"[main] {st['hook_title']} | {S.words(st)} woorden", flush=True)
    key = os.environ["PEXELS_API_KEY"]
    if a.story_file:   # alleen controleren (niet vervangen)
        bad = []
        for it in st["items"]:
            n = footage.strict_count(it, key); print(f"[main] beeld-controle nummer {it['rank']} {it['name']}: {n} passende clips", flush=True)
            if n < 6: bad.append((it["rank"], it["name"], n))
        if bad: sys.exit(f"Te weinig beeld: {bad}")
    if not a.story_file:   # poort: elk dier moet genoeg echt beeld hebben, anders vervangen
        for it in list(st["items"]):
            for att in range(3):
                n = footage.strict_count(it, key)
                print(f"[main] beeld-controle nummer {it['rank']} {it['name']}: {n} passende clips", flush=True)
                if n >= 6: break
                try: it = S.replace_item(st, it["rank"], [i["name"] for i in st["items"]])
                except Exception as e: print("[main] vervangen mislukt:", str(e)[:100], flush=True); break
            else: sys.exit(f"Geen dier met genoeg beeld voor nummer {it['rank']}")
    tl = tts.build(st, work); print(f"[main] stem klaar: {tl['total'] / 60:.1f} min", flush=True)
    lo, hi = float(os.environ.get("MIN_MINUTES", 8.1)), float(os.environ.get("MAX_MINUTES", 13))
    if not lo * 60 <= tl["total"] <= hi * 60: sys.exit(f"Lengte {tl['total'] / 60:.1f} min buiten {lo}-{hi}; niet doorgaan")
    used = set(); by = {}
    by_rank = {i["rank"]: i for i in st["items"]}
    for seg in tl["segments"]:
        if seg["name"].startswith("item"): it = by_rank[int(seg["name"][4:])]
        elif seg["name"] == "intro": it = by_rank[1]
        else: it = by_rank[2]
        clips, nstrict = footage.for_item(it, seg["dur"], key, clipdir, used); by[seg["name"]] = clips
        print(f"[main] beeld {seg['name']:7s} {it['name']}: {len(clips)} fragmenten ({nstrict} gefilterd op diernaam)", flush=True)
    raw = render.assemble(tl["segments"], by, work)
    ass = os.path.join(work, "subs.ass"); render.make_ass(st, tl, ass)
    audio = os.path.join(work, "audio.wav"); render.mix_audio(tl, audio)
    final = os.path.join(work, "final.mp4"); render.final(raw, audio, ass, final)
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]))
    print(f"[main] eindvideo {dur / 60:.1f} min, {os.path.getsize(final) / 1e6:.0f} MB", flush=True)
    thumbp = thumb.make(os.path.join(work, "thumbnail.jpg"), by["item1"][0][0], st["thumb_text"])
    desc = description(st, tl); open(os.path.join(work, "description.txt"), "w").write(st["hook_title"] + "\n\n" + desc)
    json.dump(st, open(os.path.join(work, "story.json"), "w"), ensure_ascii=False, indent=1)
    if a.dry_run: print("[main] dry-run: niet geupload"); return
    from . import upload
    vid, real = upload.upload(final, thumbp, st["hook_title"], desc, st["tags"], a.mode)
    hist["videos"].append({"date": today, "title": st["hook_title"], "theme": st.get("theme", ""), "queue_file": os.path.basename(qf) if qf else None, "video_id": vid, "animals": [i["name"] for i in st["items"]],
                           "privacy": real.get("privacyStatus"), "publishAt": real.get("publishAt")})
    json.dump(hist, open(HIST, "w"), indent=1, ensure_ascii=False); shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__": main()
