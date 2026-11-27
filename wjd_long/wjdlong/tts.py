"""Nederlandse voice-over: edge-tts (gratis, neurale stem) met gTTS en espeak-ng als noodoplossing."""
import asyncio, os, re, subprocess, numpy as np, soundfile as sf

VOICE = os.environ.get("WJD_VOICE", "nl-NL-FennaNeural")
RATE = os.environ.get("WJD_RATE", "+4%")
SR = 24000


def _edge(text, out_mp3):
    import edge_tts
    async def go():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(out_mp3)
    asyncio.run(go())


def _gtts(text, out_mp3):
    from gtts import gTTS
    gTTS(text, lang="nl").save(out_mp3)


def _espeak(text, out_wav):
    subprocess.run(["espeak-ng", "-v", "nl", "-s", "155", "-w", out_wav, text], check=True)


def _kokoro_test(text, out_wav):   # alleen voor lokale tests zonder Nederlandse stem
    from kokoro_onnx import Kokoro
    k = Kokoro(os.environ.get("KOKORO_MODEL", "models/kokoro-v1.0.onnx"), os.environ.get("KOKORO_VOICES", "models/voices-v1.0.bin"))
    a, sr = k.create(text, voice="if_sara", speed=1.0, lang="it"); sf.write(out_wav, a, sr)


def synth(text, base):
    """Maakt base.wav (mono, 24 kHz). Geeft de duur in seconden terug."""
    wav = base + ".wav"
    mode = os.environ.get("WJD_TTS", "edge")
    chain = {"edge": ["edge", "gtts", "espeak"], "gtts": ["gtts", "espeak"], "espeak": ["espeak"], "test": ["kokoro_test"], "prerendered": ["prerendered"]}[mode]
    err = []
    for m in chain:
        try:
            if m == "prerendered":   # stem eerder (elders) gemaakt: WJD_VOICE_DIR/v_<segment>.mp3
                src = os.path.join(os.environ["WJD_VOICE_DIR"], os.path.basename(base) + ".mp3")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ar", str(SR), "-ac", "1", wav], check=True)
            elif m in ("edge", "gtts"):
                mp3 = base + ".mp3"; (_edge if m == "edge" else _gtts)(text, mp3)
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", str(SR), "-ac", "1", wav], check=True)
            elif m == "espeak":
                tmp = base + "_e.wav"; _espeak(text, tmp); subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ar", str(SR), "-ac", "1", wav], check=True)
            else:
                tmp = base + "_k.wav"; _kokoro_test(text, tmp); subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ar", str(SR), "-ac", "1", wav], check=True)
            a, _ = sf.read(wav)
            if len(a) > SR * 0.5:
                if m != chain[0]: print(f"[tts] let op: noodstem '{m}' gebruikt", flush=True)
                return len(a) / SR
        except Exception as e:
            err.append(f"{m}: {str(e)[:120]}")
    raise RuntimeError("Geen stem gelukt: " + " | ".join(err))


def build(story, work):
    """Segmenten: intro, nummer 10..1, outro. Geeft tijdlijn + één geluidsbestand."""
    segs = [("intro", story["intro"])] + [(f"item{i['rank']}", i["fact"]) for i in story["items"]] + [("outro", story["outro"])]
    gap = np.zeros(int(SR * 0.55), np.float32); lead = np.zeros(int(SR * 0.35), np.float32)
    parts = [lead]; t = 0.35; tl = []
    for name, text in segs:
        base = os.path.join(work, "v_" + name); d = synth(text, base)
        a, _ = sf.read(base + ".wav"); a = a.astype(np.float32)
        tl.append({"name": name, "start": t, "dur": d + 0.55, "text": text, "voice_dur": d})
        parts += [a, gap]; t += d + 0.55
    wav = np.concatenate(parts); path = os.path.join(work, "voice.wav"); sf.write(path, wav, SR)
    return {"wav": path, "segments": tl, "total": len(wav) / SR}
