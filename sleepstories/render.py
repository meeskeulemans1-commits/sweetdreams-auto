"""Beeld renderen: clips per hoofdstuk met crossfades, hoofdstukken aan elkaar, mix, intro."""
import os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw, ImageFont

XF, OV = 1.5, 2.0   # crossfade tussen clips / tussen hoofdstukken (s)
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:]); raise RuntimeError("ffmpeg faalde")


def grade(luma):
    k = max(min(1.0, 48.0 / max(luma, 1)), 0.33)
    return (f"lutyuv=y=clip(val*{k:.3f}\\,16\\,235),eq=saturation=0.8:gamma=0.97,"
            f"colorbalance=bs=0.05:gs=0.02:rs=-0.03,vignette=PI/5")


def chapter(ci, clips, target, work):
    out = os.path.join(work, f"ch{ci}.mp4")
    if os.path.exists(out): return out
    seq = []; tot = 0.0; k = 0
    while tot < target + 0.01 and k < 200:
        fn, dur, luma, _ = clips[k % len(clips)]; k += 1
        use = min(dur - 0.3, 22.0)
        need = target - tot if not seq else target - tot + XF
        if need < use: use = max(need, XF + 1)
        seq.append((fn, use, luma)); tot += use if len(seq) == 1 else use - XF
    inp = []; fl = []
    for i, (fn, use, luma) in enumerate(seq):
        inp += ["-t", f"{use + 0.2:.2f}", "-i", fn]
        fl.append(f"[{i}:v]trim=start=0:duration={use:.3f},setpts=PTS-STARTPTS,fps=24,"
                  f"scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,{grade(luma)},format=yuv420p[v{i}]")
    cur, acc = "v0", seq[0][1]
    for i in range(1, len(seq)):
        off = acc - XF
        fl.append(f"[{cur}][v{i}]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{i}]"); cur = f"x{i}"; acc = off + seq[i][1]
    run(["ffmpeg", "-y", "-loglevel", "error"] + inp + ["-filter_complex", ";".join(fl), "-map", f"[{cur}]", "-t", f"{target:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "24", out + ".tmp.mp4"])
    os.rename(out + ".tmp.mp4", out)
    print(f"[render] hoofdstuk {ci+1} klaar ({len(seq)} clips)", flush=True)
    return out


def title_card(path, title):
    im = Image.new("RGBA", (1280, 720), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    small = ImageFont.truetype(FONTS[1], 30); big = ImageFont.truetype(FONTS[0], 62)
    d.rectangle([0, 230, 1280, 500], fill=(0, 0, 0, 105))
    d.text((640, 275), "S W E E T   D R E A M S", font=small, fill=(225, 225, 245, 255), anchor="mm")
    words = title.split(); lines = [""]
    for w in words:
        if d.textlength((lines[-1] + " " + w).strip(), font=big) > 1100: lines.append(w)
        else: lines[-1] = (lines[-1] + " " + w).strip()
    y = 390 - (len(lines) - 1) * 40
    for ln in lines:
        d.text((640, y), ln, font=big, fill=(255, 255, 255, 255), anchor="mm"); y += 80
    im.save(path)


def assemble(story, tm, voice_wav, amb_wav, work, final, title):
    N = len(story["chapters"]); B = tm["bounds"]; TOTAL = tm["total"] + 24.0
    D = [(B[i + 1] if i < N - 1 else TOTAL) - B[i] for i in range(N)]
    lens = [D[i] + (OV if i < N - 1 else 0) for i in range(N)]
    # audio
    mix = os.path.join(work, "mix.m4a")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", voice_wav, "-i", amb_wav, "-filter_complex",
         "[0:a]aresample=44100,pan=stereo|c0=c0|c1=c0[v];[1:a]aresample=44100,volume=-12dB[m];"
         "[v][m]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-19:TP=-2:LRA=7,aresample=44100[a]",
         "-map", "[a]", "-t", f"{TOTAL:.2f}", "-ar", "44100", "-c:a", "aac", "-b:a", "128k", mix])
    tpng = os.path.join(work, "title.png"); title_card(tpng, title)
    inp = []; fl = []
    for i in range(N): inp += ["-i", os.path.join(work, f"ch{i}.mp4")]
    inp += ["-loop", "1", "-i", tpng, "-i", mix]
    cur, acc = "0:v", lens[0]
    for i in range(1, N):
        off = acc - OV
        fl.append(f"[{cur}][{i}:v]xfade=transition=fade:duration={OV}:offset={off:.3f}[x{i}]"); cur = f"x{i}"; acc = off + lens[i]
    fl.append(f"[{N}:v]format=rgba,fade=t=in:st=2:d=2:alpha=1,fade=t=out:st=10:d=3:alpha=1[t]")
    fl.append(f"[{cur}][t]overlay=0:0:eof_action=pass,fade=t=in:st=0:d=3,fade=t=out:st={TOTAL-6:.2f}:d=6[v]")
    run(["ffmpeg", "-y", "-loglevel", "error"] + inp + ["-filter_complex", ";".join(fl), "-map", "[v]", "-map", f"{N+1}:a",
         "-t", f"{TOTAL:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-maxrate", "1400k", "-bufsize", "3500k",
         "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "copy", "-movflags", "+faststart", final])
    return TOTAL


def prepend_intro(main, intro, out, work):
    a = os.path.join(work, "intro_v.mp4"); b = os.path.join(work, "main_v.mp4"); lst = os.path.join(work, "list.txt")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-an", "-c:v", "copy", a])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", main, "-an", "-c:v", "copy", b])
    open(lst, "w").write(f"file '{os.path.abspath(a)}'\nfile '{os.path.abspath(b)}'\n")
    va = os.path.join(work, "video_all.mp4"); aa = os.path.join(work, "audio_all.m4a")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", va])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-i", main, "-filter_complex",
         "[0:a]aresample=44100[a0];[1:a]aresample=44100[a1];[a0][a1]concat=n=2:v=0:a=1[a]", "-map", "[a]",
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", aa])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", va, "-i", aa, "-map", "0:v", "-map", "1:a", "-c", "copy",
         "-movflags", "+faststart", out])
    return out


def render_all(story, tm, clips, voice_wav, amb_wav, work, final_noint, title, workers=2):
    N = len(story["chapters"]); B = tm["bounds"]; TOTAL = tm["total"] + 24.0
    D = [(B[i + 1] if i < N - 1 else TOTAL) - B[i] for i in range(N)]
    targets = [D[i] + (OV if i < N - 1 else 0) for i in range(N)]
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda i: chapter(i, clips[i], targets[i], work), range(N)))
    return assemble(story, tm, voice_wav, amb_wav, work, final_noint, title)
