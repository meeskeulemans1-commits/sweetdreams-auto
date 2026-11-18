"""Stem met Kokoro (gratis, lokaal). Resume per alinea."""
import json, os, urllib.request
import numpy as np, soundfile as sf

SR = 24000
LEAD = 2.5          # stilte voor de eerste zin
GAP_PARA, GAP_CHAPTER = 1.3, 3.0
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"


def ensure_models(d="models"):
    os.makedirs(d, exist_ok=True)
    for fn in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(d, fn)
        if not os.path.exists(p):
            print("[tts] downloading", fn, flush=True)
            urllib.request.urlretrieve(BASE + fn, p)
    return d


def synthesize(story, work, models="models", voice="af_nicole", speed=0.82):
    from kokoro_onnx import Kokoro
    d = ensure_models(models)
    k = Kokoro(os.path.join(d, "kokoro-v1.0.onnx"), os.path.join(d, "voices-v1.0.bin"))
    par = os.path.join(work, "par"); os.makedirs(par, exist_ok=True)
    out = [np.zeros(int(SR * LEAD), np.float32)]
    pos = LEAD; starts = []
    for ci, ch in enumerate(story["chapters"]):
        starts.append(pos)
        n = len(ch["paragraphs"])
        for pi, text in enumerate(ch["paragraphs"]):
            fn = os.path.join(par, f"{ci}_{pi}.npy")
            if not os.path.exists(fn):
                a, sr = k.create(text.replace("\n", " "), voice=voice, speed=speed, lang="en-us")
                assert sr == SR
                np.save(fn, a.astype(np.float32))
            a = np.load(fn)
            gap = np.zeros(int(SR * (GAP_PARA if pi < n - 1 else GAP_CHAPTER)), np.float32)
            out += [a, gap]; pos += (len(a) + len(gap)) / SR
        print(f"[tts] chapter {ci+1}/{len(story['chapters'])} done, {pos/60:.1f} min", flush=True)
    wav = os.path.join(work, "voice.wav")
    sf.write(wav, np.concatenate(out), SR)
    # hoofdstuk 0 begint in beeld bij t=0; de andere bij hun stemtijd
    bounds = [0.0] + starts[1:]
    return {"wav": wav, "total": pos, "bounds": bounds, "starts": starts}
