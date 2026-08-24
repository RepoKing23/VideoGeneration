#!/usr/bin/env python3
"""Synthesise a lo-fi bed sized to a reel.

Written rather than licensed, so there is no rights question about using it
commercially. It is deliberately simple: soft seventh-chord keys, a lazy
two-and-four beat, upright-ish bass and vinyl noise, all rolled off at the top
the way the genre expects.

    python3 scripts/make_lofi.py out.wav --duration 18 --bpm 72
"""
from __future__ import annotations

import argparse
import wave

import numpy as np

SR = 44100

# Am7 - Dm7 - G7 - Cmaj7, one bar each. Warm, unresolved, stays out of the way.
PROGRESSION = [
    [57, 60, 64, 67],
    [50, 53, 57, 60],
    [55, 59, 62, 65],
    [48, 52, 55, 59],
]


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n: int, attack: float, decay: float) -> np.ndarray:
    a = max(1, int(attack * SR))
    e = np.exp(-np.linspace(0, 1, n) * decay)
    e[:a] *= np.linspace(0, 1, a)
    return e


def key_note(midi: float, dur: float, gain: float, rng) -> np.ndarray:
    """Electric-piano-ish: a few harmonics, soft attack, long decay."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    detune = 1 + rng.uniform(-0.0016, 0.0016)
    f = hz(midi) * detune
    sig = (np.sin(2 * np.pi * f * t)
           + 0.32 * np.sin(2 * np.pi * 2 * f * t)
           + 0.11 * np.sin(2 * np.pi * 3 * f * t)
           + 0.05 * np.sin(2 * np.pi * 4.01 * f * t))
    return sig * env(n, 0.018, 3.6) * gain


def bass_note(midi: float, dur: float, gain: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi - 12)
    sig = np.sin(2 * np.pi * f * t) + 0.18 * np.sin(2 * np.pi * 2 * f * t)
    return sig * env(n, 0.012, 4.2) * gain


def kick(gain: float) -> np.ndarray:
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    f = 115 * np.exp(-t * 26) + 44          # pitch drops into the fundamental
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 13) * gain


def snare(gain: float, rng) -> np.ndarray:
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    body = np.sin(2 * np.pi * 190 * t) * 0.4
    return (noise * 0.7 + body) * np.exp(-t * 19) * gain


def hat(gain: float, rng) -> np.ndarray:
    n = int(0.07 * SR)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    noise = np.diff(noise, prepend=0)        # crude high-pass
    return noise * np.exp(-t * 62) * gain * 0.55


def add(buf: np.ndarray, sig: np.ndarray, at: float) -> None:
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def lowpass(x: np.ndarray, cutoff: float, taps: int = 255) -> np.ndarray:
    """Windowed-sinc low-pass.

    A one-pole rolls off at 6 dB/octave, which barely touches the top end -
    the first pass at this left 40% of the energy above 6 kHz, far too bright
    for the genre. This is steep enough to actually sound rolled off.
    """
    if taps % 2 == 0:
        taps += 1
    m = (taps - 1) // 2
    k = np.arange(-m, m + 1)
    fc = cutoff / SR
    h = np.sinc(2 * fc * k) * np.hamming(taps)
    h /= h.sum()
    return np.convolve(x, h, mode="same")


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthesise a lo-fi bed.")
    ap.add_argument("output")
    ap.add_argument("--duration", type=float, default=18.0)
    ap.add_argument("--bpm", type=float, default=72.0)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    beat = 60.0 / args.bpm
    bar = beat * 4
    total = args.duration + 3.0            # tail so the last chord can ring
    n = int(total * SR)
    keys = np.zeros(n); bass = np.zeros(n); drums = np.zeros(n)

    bars = int(np.ceil(total / bar))
    for b in range(bars):
        t0 = b * bar
        chord = PROGRESSION[b % len(PROGRESSION)]
        # Chord on the downbeat, second voicing pushed late for a lazy feel.
        for k, m in enumerate(chord):
            add(keys, key_note(m, 3.2, 0.20, rng), t0 + k * 0.012)
        for k, m in enumerate(chord[1:]):
            add(keys, key_note(m + 12, 2.2, 0.075, rng), t0 + beat * 2.5 + k * 0.02)
        add(bass, bass_note(chord[0], 1.6, 0.42), t0)
        add(bass, bass_note(chord[0], 1.0, 0.24), t0 + beat * 2.5)

        add(drums, kick(0.62), t0)
        add(drums, kick(0.40), t0 + beat * 2.5)
        add(drums, snare(0.30, rng), t0 + beat)
        add(drums, snare(0.30, rng), t0 + beat * 3)
        for e in range(8):                  # swung eighths
            swing = 0.055 * beat if e % 2 else 0.0
            add(drums, hat(0.08 if e % 2 else 0.12, rng),
                t0 + e * beat / 2 + swing)

    mix = keys + bass + drums

    # Vinyl: steady hiss plus occasional pops.
    hiss = lowpass(rng.normal(0, 1, n), 3200) * 0.010
    pops = np.zeros(n)
    for at in rng.uniform(0, total, int(total * 7)):
        i = int(at * SR)
        if i < n - 60:
            pops[i:i + 60] += rng.normal(0, 1, 60) * np.exp(-np.linspace(0, 1, 60) * 7) * 0.05
    mix += hiss + pops

    # Lo-fi voicing: roll off the top hard, then soften the peaks.
    mix = lowpass(mix, 3800)
    mix = np.tanh(mix * 1.25) * 0.8

    out = mix[: int(args.duration * SR)]
    fade = int(0.9 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out[:int(0.25 * SR)] *= np.linspace(0, 1, int(0.25 * SR))
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.89

    stereo = np.stack([out, np.roll(out, 90)], axis=1)   # slight width
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(args.output, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(f"wrote {args.output}  {args.duration:.2f}s  {args.bpm:g} bpm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
