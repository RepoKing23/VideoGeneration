#!/usr/bin/env python3
"""Synthesise a zen/spa ambient bed sized to a reel.

Written rather than licensed, so there is no rights question about using it
commercially. Where make_lofi.py aims for a lazy beat, this aims for no beat
at all: slow-breathing pad chords, a quiet root drone, sparse pentatonic
bells and an ocean-like air swell. Everything eases in and out - nothing
attacks harder than a breath.

    python3 scripts/make_ambient.py out.wav --duration 40
"""
from __future__ import annotations

import argparse
import wave

import numpy as np

SR = 44100

# Aadd9 - Fmaj9 - Cmaj9 - Gsus2, dwelling on each. Open voicings, no leading
# tones, so the ear never expects a resolution - it just floats.
PROGRESSION = [
    [45, 52, 57, 59, 64],
    [41, 48, 55, 57, 60],
    [36, 48, 52, 55, 62],
    [43, 50, 55, 57, 62],
]

# Bell notes come from the A minor pentatonic two octaves up; every note in it
# is consonant against every chord above, so placement can be loose.
BELL_POOL = [69, 72, 74, 76, 79, 81]


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def smooth_env(n: int, attack: float, release: float) -> np.ndarray:
    """Cosine-eased attack and release; flat sustain between."""
    a = min(n // 2, max(1, int(attack * SR)))
    r = min(n - a, max(1, int(release * SR)))
    e = np.ones(n)
    e[:a] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a))
    e[n - r:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r))
    return e


def pad_note(midi: float, dur: float, gain: float, rng) -> np.ndarray:
    """Soft pad voice: detuned pair of dark partial stacks with a slow
    amplitude shimmer, so held chords keep moving slightly."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for detune in (1 - 0.0011, 1 + 0.0013):
        f = hz(midi) * detune
        phase = rng.uniform(0, 2 * np.pi)
        sig += (np.sin(2 * np.pi * f * t + phase)
                + 0.22 * np.sin(2 * np.pi * 2 * f * t + phase * 1.7)
                + 0.05 * np.sin(2 * np.pi * 3 * f * t))
    lfo = 1 + 0.10 * np.sin(2 * np.pi * rng.uniform(0.06, 0.12) * t
                            + rng.uniform(0, 2 * np.pi))
    return sig * lfo * smooth_env(n, 2.6, 3.4) * gain


def drone_note(midi: float, dur: float, gain: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi - 12)
    sig = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t)
    return sig * smooth_env(n, 3.0, 4.0) * gain


def bell(midi: float, gain: float, rng) -> np.ndarray:
    """Singing-bowl-ish strike: fundamental plus slightly inharmonic upper
    partials, each decaying at its own rate, with a gentle onset."""
    dur = 6.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(midi)
    sig = (np.sin(2 * np.pi * f * t) * np.exp(-t * 0.55)
           + 0.38 * np.sin(2 * np.pi * f * 2.71 * t) * np.exp(-t * 1.3)
           + 0.16 * np.sin(2 * np.pi * f * 5.18 * t) * np.exp(-t * 2.6))
    beat_lfo = 1 + 0.18 * np.sin(2 * np.pi * rng.uniform(0.7, 1.3) * t)
    onset = min(n, int(0.030 * SR))
    sig[:onset] *= np.linspace(0, 1, onset)
    return sig * beat_lfo * gain


def add(buf: np.ndarray, sig: np.ndarray, at: float) -> None:
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def lowpass(x: np.ndarray, cutoff: float, taps: int = 255) -> np.ndarray:
    if taps % 2 == 0:
        taps += 1
    m = (taps - 1) // 2
    k = np.arange(-m, m + 1)
    fc = cutoff / SR
    h = np.sinc(2 * fc * k) * np.hamming(taps)
    h /= h.sum()
    return np.convolve(x, h, mode="same")


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthesise a zen ambient bed.")
    ap.add_argument("output")
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--chord-seconds", type=float, default=9.0)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    hold = args.chord_seconds
    total = args.duration + 4.0             # tail so the last pad can ring
    n = int(total * SR)
    pads = np.zeros(n); drone = np.zeros(n); bells = np.zeros(n)

    chords = int(np.ceil(total / hold))
    for c in range(chords):
        t0 = c * hold
        chord = PROGRESSION[c % len(PROGRESSION)]
        # Notes drift in one after another; overlap into the next chord makes
        # the changes crossfade instead of stepping.
        for k, m in enumerate(chord):
            add(pads, pad_note(m, hold + 4.5, 0.16 - 0.012 * k, rng),
                t0 + k * rng.uniform(0.25, 0.7))
        add(drone, drone_note(chord[0], hold + 5.0, 0.16), t0)

    # Sparse bells on a loose grid: roughly one per breath, never two close
    # together, skipping the very start so the pad establishes the mood first.
    at = rng.uniform(3.5, 5.5)
    while at < total - 6:
        add(bells, bell(float(rng.choice(BELL_POOL)), rng.uniform(0.05, 0.085), rng), at)
        at += rng.uniform(5.5, 9.0)

    # Air: band-limited noise breathing on a ~10 s cycle, like slow surf.
    t = np.arange(n) / SR
    breath = 0.55 + 0.45 * np.sin(2 * np.pi * t / 10.5 - np.pi / 2)
    air = lowpass(rng.normal(0, 1, n), 950) * breath * 0.020

    mix = pads + drone + bells + air
    mix = lowpass(mix, 5200)                # keep the top end soft
    mix = np.tanh(mix * 1.1) * 0.85

    out = mix[: int(args.duration * SR)]
    fade_in = int(1.2 * SR); fade_out = int(1.6 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    peak = np.max(np.abs(out)) or 1.0
    out = out / peak * 0.85

    stereo = np.stack([out, np.roll(out, 130)], axis=1)  # slight width
    data = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    with wave.open(args.output, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(f"wrote {args.output}  {args.duration:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
