#!/usr/bin/env python3
"""Render an animated before/after split-reveal clip.

A vertical divider sweeps across the frame: everything left of it is the
BEFORE image, everything right of it is the AFTER. Sweeping it back and forth
and settling on a centre split gives the comparison people actually stop for.

The two images must already be aligned and colour-matched - if the mouth line
jumps across the divider, or one side is brighter, the effect reads as a
mistake rather than a result. scripts/prep_photos.py handles both.

Frames are composited in PIL and piped to ffmpeg. That is far easier to reason
about (and to verify) than a time-varying crop expression in a filtergraph.

    python3 scripts/split_reveal.py before.jpg after.jpg out.mp4 --duration 4.2
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "media" / "fonts"


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def divider_at(t: float, keys: list[tuple[float, float]]) -> float:
    """Position of the divider at time t, easing between keyframes."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * smoothstep((t - t0) / (t1 - t0))
    return keys[-1][1]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("Poppins-SemiBold.ttf", "Poppins-Medium.ttf", "Anton-Regular.ttf"):
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def label(draw: ImageDraw.ImageDraw, text: str, cx: int, cy: int,
          font: ImageFont.FreeTypeFont, alpha: int) -> None:
    if alpha <= 2:
        return
    box = draw.textbbox((0, 0), text, font=font)
    x, y = cx - (box[2] - box[0]) // 2, cy - (box[3] - box[1]) // 2
    for ox in (-3, 0, 3):
        for oy in (-3, 0, 3):
            if ox or oy:
                draw.text((x + ox, y + oy), text, font=font, fill=(20, 14, 12, alpha))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))


def main() -> int:
    ap = argparse.ArgumentParser(description="Animated before/after split reveal.")
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("output")
    ap.add_argument("--duration", type=float, default=4.2)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--labels", action="store_true", default=True)
    ap.add_argument("--no-labels", dest="labels", action="store_false")
    ap.add_argument("--label-size", type=int, default=76)
    ap.add_argument("--line-width", type=int, default=7)
    args = ap.parse_args()

    before = Image.open(args.before).convert("RGB")
    after = Image.open(args.after).convert("RGB")
    if before.size != after.size:
        after = after.resize(before.size, Image.LANCZOS)
    W, H = before.size

    d = args.duration
    # 1.0 = all before, 0.0 = all after, 0.5 = the centre split people expect.
    keys = [
        (0.00,          1.0),
        (0.13 * d,      1.0),
        (0.34 * d,      0.0),   # sweep across, revealing the result
        (0.46 * d,      0.0),
        (0.62 * d,      1.0),   # snap back for the comparison
        (0.69 * d,      1.0),
        (0.86 * d,      0.5),   # settle on the split
        (d,             0.5),
    ]

    font = load_font(args.label_size)
    total = int(round(d * args.fps))
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", args.output],
        stdin=subprocess.PIPE)

    for i in range(total):
        t = i / args.fps
        pos = divider_at(t, keys)
        x = int(round(pos * W))

        frame = after.copy()
        if x > 0:
            frame.paste(before.crop((0, 0, x, H)), (0, 0))

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if args.labels:
            fade = lambda v: int(max(0.0, min(1.0, v)) * 255)
            label(draw, "BEFORE", int(W * 0.25), int(H * 0.83), font,
                  fade((pos - 0.30) / 0.16))
            label(draw, "AFTER", int(W * 0.75), int(H * 0.83), font,
                  fade((0.70 - pos) / 0.16))
        # The line only exists while there are two sides to divide.
        edge = min(pos, 1 - pos)
        if edge > 0.001:
            a = int(min(1.0, edge / 0.04) * 255)
            half = args.line_width // 2
            draw.rectangle([x - half - 2, 0, x + half + 2, H], fill=(0, 0, 0, a // 3))
            draw.rectangle([x - half, 0, x + half, H], fill=(255, 255, 255, a))

        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding the split reveal")
    print(f"wrote {args.output}  {W}x{H}  {d:.2f}s  {total} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
