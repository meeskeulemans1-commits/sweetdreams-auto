"""Zelfgemaakte rustige pad-akkoorden + zachte belletjes (geen auteursrecht)."""
import wave, random
import numpy as np
from scipy.signal import lfilter

SR = 22050
CHORDS = [[220, 329.6, 440, 493.9], [174.6, 261.6, 349.2, 440], [261.6, 392, 523.3, 659.3], [196, 293.7, 392, 493.9],
          [220, 329.6, 415.3, 493.9], [146.8, 220, 293.7, 370], [174.6, 261.6, 329.6, 440], [196, 246.9, 392, 587.3]]


def lp(x, fc):
    a = np.exp(-2 * np.pi * fc / SR)
    return lfilter([1 - a], [1, -a], x)


def make(path, D, seed=None):
    seed = random.randrange(10**6) if seed is None else seed
    rng = np.random.default_rng(seed)
    n = int(SR * D); t = np.arange(n, dtype=np.float32) / SR
    order = list(range(len(CHORDS))); rng.shuffle(order)
    seg = float(rng.uniform(60, 80)); nseg = int(D // seg) + 2
    pad = np.zeros(n, np.float32)
    for i in range(nseg):
        ch = CHORDS[order[i % len(order)]]; c = (i + 0.5) * seg
        env = np.exp(-0.5 * ((t - c) / (seg * 0.42)) ** 2)
        for k, f in enumerate(ch):
            pad += (env * (0.5 / (1 + 0.25 * k)) * np.sin(2 * np.pi * f * t + k * 1.3 + i)).astype(np.float32)
    pad = lp(pad, 900)
    bells = np.zeros(n, np.float32)
    notes = [440, 523.3, 587.3, 659.3, 784, 880]; tt = 6.0
    while tt < D - 10:
        f = notes[rng.integers(len(notes))]; i0 = int(tt * SR); m = min(int(7 * SR), n - i0); x = np.arange(m) / SR
        bells[i0:i0 + m] += ((np.sin(2 * np.pi * f * x) + 0.25 * np.sin(2 * np.pi * 2 * f * x)) * np.exp(-x / 1.6) * (1 - np.exp(-x / 0.05)) * 0.5).astype(np.float32)
        tt += rng.uniform(9, 17)
    bells = lp(bells, 2500)
    mix = pad / np.max(np.abs(pad)) * 0.8 + bells / max(np.max(np.abs(bells)), 1e-6) * 0.16
    mix /= np.max(np.abs(mix))
    mix *= np.minimum(1, np.minimum(t / 6, (D - t) / 10)) * 0.33
    r = np.roll(mix, int(0.012 * SR))
    pcm = (np.stack([mix, r], 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(SR); f.writeframes(pcm.tobytes())
    return path
