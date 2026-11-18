"""Pexels-stockbeeld zoeken, downloaden en op helderheid meten."""
import math, os, subprocess, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import numpy as np, requests

API = "https://api.pexels.com/videos/search"
FALLBACK = ["night sky stars", "moon clouds", "calm water", "candle flame", "forest mist", "gentle rain window",
            "starry night timelapse", "soft waves sunset", "snow falling night", "fireplace"]
UA = {"User-Agent": "Mozilla/5.0"}


def search(query, key, page=1):
    r = requests.get(API, params={"query": query, "per_page": 15, "page": page, "orientation": "landscape", "size": "large"},
                     headers={"Authorization": key, **UA}, timeout=40)
    r.raise_for_status()
    return r.json().get("videos", [])


def pick_file(v):
    fs = [f for f in v["video_files"] if f.get("width") and f.get("file_type") == "video/mp4" and 1280 <= f["width"] <= 1920]
    return sorted(fs, key=lambda f: f["width"])[0] if fs else None


def candidates(queries, key, exclude, need):
    """Round-robin over queries, pagina 1-3, tot er 'need' clips zijn."""
    seen = set(exclude); out = []
    for page in (1, 2, 3):
        byq = {}
        for q in queries:
            try:
                for v in search(q, key, page):
                    f = pick_file(v)
                    if v["id"] in seen or not f or not 8 <= v["duration"] <= 45: continue
                    byq.setdefault(q, []).append((v["id"], v["duration"], f["link"]))
            except Exception as e:
                print("[pexels] fout", q, e, flush=True)
        while any(byq.values()) and len(out) < need:
            for q in list(byq):
                if byq[q] and len(out) < need:
                    c = byq[q].pop(0)
                    if c[0] not in seen: seen.add(c[0]); out.append(c)
        if len(out) >= need: break
    return out


def download(item, folder):
    vid, dur, link = item
    fn = os.path.join(folder, f"{vid}.mp4")
    if not os.path.exists(fn):
        with requests.get(link, headers=UA, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(fn + ".part", "wb") as f:
                for b in r.iter_content(1 << 20): f.write(b)
        os.rename(fn + ".part", fn)
    return fn


def luma(fn):
    """Gemiddelde helderheid 0-255 uit 3 frames."""
    vals = []
    for ss in (1.0, 4.0, 7.0):
        p = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(ss), "-i", fn, "-frames:v", "1", "-vf", "scale=64:36,format=gray",
                            "-f", "rawvideo", "-"], capture_output=True)
        if len(p.stdout) == 64 * 36: vals.append(float(np.frombuffer(p.stdout, np.uint8).mean()))
    return sum(vals) / len(vals) if vals else 60.0


def gather(story, key, durations, exclude, work):
    """Geeft per hoofdstuk een lijst (bestand, duur, luma) en alle gebruikte ids."""
    folder = os.path.join(work, "clips"); os.makedirs(folder, exist_ok=True)
    used = set(exclude); chapters = []
    for ci, ch in enumerate(story["chapters"]):
        need = math.ceil(durations[ci] / 13) + 4
        cand = candidates(ch["pexels_queries"], key, used, need)
        if len(cand) < need:
            cand += candidates(FALLBACK, key, used | {c[0] for c in cand}, need - len(cand))
        if not cand: raise RuntimeError(f"Geen beeld gevonden voor hoofdstuk {ci+1}")
        with ThreadPoolExecutor(6) as ex:
            files = list(ex.map(lambda c: download(c, folder), cand))
        info = []
        for c, fn in zip(cand, files):
            used.add(c[0]); info.append((fn, float(c[1]), luma(fn), c[0]))
        chapters.append(info)
        print(f"[footage] hoofdstuk {ci+1}: {len(info)} clips", flush=True)
    return chapters
