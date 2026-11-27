"""Pexels-stockbeeld per dier: zoeken, op diernaam filteren, downloaden."""
import math, os, re
import requests

API = "https://api.pexels.com/videos/search"
UA = {"User-Agent": "Mozilla/5.0"}
SEG = 5.5   # gemiddelde duur per fragment


_CACHE = {}


def _search(q, key, page=1):
    """Zoekt met schijfcache en wacht bij het uurlimiet (429) tot het weer mag."""
    import json, time
    ck = f"{q}|{page}"
    if ck in _CACHE: return _CACHE[ck]
    cf = os.environ.get("WJD_SEARCH_CACHE")
    disk = {}
    if cf and os.path.exists(cf):
        try: disk = json.load(open(cf))
        except Exception: disk = {}
    if ck in disk: _CACHE[ck] = disk[ck]; return disk[ck]
    for att in range(80):
        r = requests.get(API, params={"query": q, "per_page": 20, "page": page, "orientation": "landscape", "size": "large"}, headers={"Authorization": key, **UA}, timeout=40)
        if r.status_code == 429: print("[pexels] uurlimiet bereikt, wacht 60s", flush=True); time.sleep(60); continue
        r.raise_for_status(); break
    else: raise RuntimeError("Pexels blijft 429 geven")
    v = r.json().get("videos", []); _CACHE[ck] = v
    if cf:
        disk[ck] = v; json.dump(disk, open(cf, "w"))
    return v


def _file(v):
    fs = [f for f in v["video_files"] if f.get("width") and f.get("file_type") == "video/mp4" and 1280 <= f["width"] <= 1920]
    return sorted(fs, key=lambda f: f["width"])[0] if fs else None


def _stem(name):
    w = re.sub(r"[^a-z ]", "", name.lower()).split()[-1] if name.strip() else ""
    for suf in ("ies", "es", "s"):
        if w.endswith(suf) and len(w) > 4: return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


EXCL = re.compile(r"praying|cricket|baseball|batting|batter|softball|combat|wombat|acrobat|crowd|crown|decor|cutout|silhouette|costume|halloween|child|kid-|-kid|boy|girl|woman|man-|person|toy|paper|cartoon|plush|drawing|illustration")
# Strikte naamsfilters (regex-stam op de pexels-url); anders volgt het stam uit de Engelse naam
OVERRIDE = {"mantis shrimp": "mantis", "new caledonian crow": "crow|raven", "sperm whale": "whale", "sea otter": "otter", "bat": "bat", "jellyfish": "jelly ?fish|jelly-fish|jellies"}


def _match(item, url):
    url = url.lower()
    if EXCL.search(url): return False
    eng = item["english"].lower().strip()
    pat = OVERRIDE.get(eng) or re.escape(_stem(eng))
    pat = pat.replace(" ", "-") if "|" not in pat else pat
    return bool(re.search(r"(?<![a-z])(?:" + pat + r")(?:s|es)?(?![a-z])", url))


def _download(link, fn):
    if os.path.exists(fn): return fn
    with requests.get(link, headers=UA, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(fn + ".part", "wb") as f:
            for b in r.iter_content(1 << 20): f.write(b)
    os.replace(fn + ".part", fn); return fn


def for_item(item, need_s, key, folder, used):
    """Geeft lijst (pad, duur) die samen ≥ need_s seconden beeld geven."""
    stem = _stem(item["english"]); n_need = max(2, math.ceil(need_s / SEG))
    qs = item["queries"] + [item["english"]]
    cands, strict = [], []
    for page in (1, 2):
        for q in qs:
            try: vs = _search(q, key, page)
            except Exception as e: print("[pexels] fout", q, str(e)[:80], flush=True); continue
            for v in vs:
                f = _file(v)
                if v["id"] in used or not f or not 4 <= v["duration"] <= 60: continue
                row = (v["id"], v["duration"], f["link"])
                (strict if _match(item, v.get("url", "")) else cands).append(row)
        if len(strict) >= n_need: break
    pool = strict if len(strict) >= 4 else strict + cands
    seen, out, total = set(), [], 0.0
    for vid, dur, link in pool:
        if vid in seen: continue
        seen.add(vid)
        try: fn = _download(link, os.path.join(folder, f"{vid}.mp4"))
        except Exception as e: print("[pexels] download mislukt", vid, str(e)[:80], flush=True); continue
        use = min(dur, SEG + 1.5); out.append((fn, use, vid)); used.add(vid); total += use
        if total >= need_s + 1: break
    while out and total < need_s - 0.5 and len(strict) >= 4:   # te weinig echte clips: dezelfde herhalen, nooit ander beeld erbij
        for fn, use, vid in list(out):
            out.append((fn, use, vid)); total += use
            if total >= need_s - 0.5: break
    if total < need_s - 0.5: print(f"[pexels] let op: {item['name']} heeft maar {total:.0f}s van {need_s:.0f}s beeld", flush=True)
    if not out: raise RuntimeError(f"Geen beeld voor {item['name']}")
    return out, len(strict)


def strict_count(item, key):
    """Hoeveel clips met de diernaam in de URL bestaan er? (poort tegen verkeerd of generiek beeld)"""
    stem = _stem(item["english"]); n = set()
    for q in item["queries"][:2] + [item["english"]]:
        try:
            for v in _search(q, key, 1):
                if _match(item, v.get("url", "")) and _file(v) and 4 <= v["duration"] <= 60: n.add(v["id"])
        except Exception as e: print("[pexels] fout", q, str(e)[:80], flush=True)
    return len(n)
