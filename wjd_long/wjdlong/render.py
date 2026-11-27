"""Video renderen: fragmenten op maat knippen, aaneenplakken, daarna grafiek en ondertitels erover en de stem eronder."""
import os, subprocess, re, numpy as np, soundfile as sf

FONTS = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
W, H, FPS = 1920, 1080, 30


def run(cmd): subprocess.run(cmd, check=True)


def cut(src, start, dur, out, vf_extra=""):
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1{vf_extra}"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.3f}", "-i", src, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "19", "-pix_fmt", "yuv420p", out])


def assemble(segments, clips_by_seg, work):
    """segments: tijdlijn uit tts; clips_by_seg: naam -> [(pad, duur, id)]. Geeft pad naar video zonder geluid."""
    pieces = []; n = 0
    for seg in segments:
        need = seg["dur"]; clips = clips_by_seg[seg["name"]]
        k = len(clips); per = need / k
        for i, (fn, dur, vid) in enumerate(clips):
            d = per if i < k - 1 else need - per * (k - 1)
            out = os.path.join(work, f"p{n:03d}.mp4"); n += 1
            start = 0.0 if dur <= d + 0.2 else max(0.0, (dur - d) / 2 - 0.3)
            if dur < d - 0.1:   # fragment te kort: vertraag licht (max 0.75x) en herhaal anders de laatste beelden
                f = max(0.75, dur / d); cut(fn, 0, dur, out + ".s.mp4", f",setpts=PTS/{f:.4f}")
                run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "3", "-i", out + ".s.mp4", "-t", f"{d:.3f}", "-c", "copy", out])
            else:
                cut(fn, start, d, out)
            pieces.append(out)
    lst = os.path.join(work, "list.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in pieces))
    v = os.path.join(work, "video_raw.mp4"); run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", v])
    return v


def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def captions(seg, maxw=7):
    """Zinnen in korte ondertitelregels; tijd verdeeld op tekenlengte."""
    sents = re.split(r"(?<=[.!?])\s+", seg["text"]); lines = []
    for s in sents:
        w = s.split(); k = max(1, -(-len(w) // maxw)); per = -(-len(w) // k)
        for i in range(0, len(w), per): lines.append(" ".join(w[i:i + per]))
    tot = sum(len(l) + 1 for l in lines); t = seg["start"]; out = []
    for l in lines:
        d = seg["voice_dur"] * (len(l) + 1) / tot; out.append((l, t, t + d)); t += d
    return out


def make_ass(story, tl, path):
    def esc(s): return s.replace("{", "(").replace("}", ")")
    hdr = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "", "[V4+ Styles]",
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
           "Style: Cap,Poppins,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,2,2,120,120,70,1",
           "Style: Rank,Poppins ExtraBold,190,&H0030D5FF,&H0030D5FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,9,4,7,60,60,20,1",
           "Style: Name,Poppins,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,2,0,1,7,3,7,70,60,215,1",
           "Style: Tag,Poppins,38,&H00FFFFFF,&H00FFFFFF,&H003030D0,&H80000000,-1,0,0,0,100,100,2,0,3,10,0,9,40,40,36,1",
           "Style: Big,Poppins ExtraBold,120,&H0030D5FF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,10,4,5,120,120,60,1",
           "Style: Cta,Poppins ExtraBold,96,&H00FFFFFF,&H00FFFFFF,&H003030D0,&H90000000,-1,0,0,0,100,100,0,0,3,18,0,5,120,120,60,1", "",
           "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    ev = []
    total = tl["total"]
    ev.append(f"Dialogue: 2,{ts(0)},{ts(total)},Tag,,0,0,0,,TOP 10 DIEREN")
    for seg in tl["segments"]:
        for l, a, b in captions(seg): ev.append(f"Dialogue: 1,{ts(a)},{ts(b + 0.05)},Cap,,0,0,0,,{esc(l)}")
        if seg["name"].startswith("item"):
            rank = int(seg["name"][4:]); it = next(i for i in story["items"] if i["rank"] == rank)
            a, b = seg["start"], seg["start"] + seg["dur"] - 0.2
            ev.append(f"Dialogue: 2,{ts(a)},{ts(b)},Rank,,0,0,0,,{{\\fad(120,200)\\t(0,180,\\fscx118\\fscy118)\\t(180,360,\\fscx100\\fscy100)}}#{rank}")
            ev.append(f"Dialogue: 2,{ts(a + 0.15)},{ts(b)},Name,,0,0,0,,{{\\fad(200,200)\\move(40,245,70,245,0,250)}}{esc(it['name'].upper())}")
        elif seg["name"] == "intro":
            ev.append(f"Dialogue: 2,{ts(0.4)},{ts(min(seg['start'] + seg['dur'] - 0.4, 6.0))},Big,,0,0,0,,{{\\fad(200,300)\\t(0,300,\\fscx110\\fscy110)\\t(300,500,\\fscx100\\fscy100)}}{esc(story['thumb_text'])}")
        elif seg["name"] == "outro":
            a = seg["start"] + max(1.0, seg["voice_dur"] - 6.0)
            ev.append(f"Dialogue: 2,{ts(a)},{ts(total)},Cta,,0,0,0,,{{\\fad(200,300)}}ABONNEER")
    open(path, "w").write("\n".join(hdr + ev))


def whoosh(sr, dur=0.5):
    n = int(sr * dur); rng = np.random.default_rng(3); x = rng.standard_normal(n)
    from scipy.signal import butter, lfilter
    out = np.zeros(n)
    for i in range(0, n, 512):   # zwiepende ruis: bandfilter schuift omhoog
        c = 400 + 3500 * (i / n); b, a = butter(2, [c / (sr / 2) * 0.7, min(0.95, c / (sr / 2) * 1.3)], "band"); out[i:i + 512] = lfilter(b, a, x[i:i + 512])
    env = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return (out * env / (np.abs(out * env).max() + 1e-9) * 0.22).astype(np.float32)


def mix_audio(tl, path):
    a, sr = sf.read(tl["wav"]); a = a.astype(np.float32)
    bed = np.zeros(len(a), np.float32); w = whoosh(sr)
    for seg in tl["segments"]:
        if seg["name"].startswith("item"):
            s = max(0, int((seg["start"] - 0.35) * sr)); e = min(len(bed), s + len(w)); bed[s:e] += w[: e - s]
    sf.write(path, np.clip(a + bed, -1, 1), sr)


def final(video_raw, audio, ass, out):
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_raw, "-i", audio, "-vf", f"subtitles={ass}:fontsdir={os.path.abspath(FONTS)}",
         "-af", "loudnorm=I=-15:TP=-1.5:LRA=9", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-shortest", "-movflags", "+faststart", out])
