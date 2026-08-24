#!/usr/bin/env python3
"""Handwriting-style intro title over a still, CapCut-like.

The look, copied from the reference reel: large white script text revealed
letter by letter with a soft glow, a small semi-transparent sun doodle, diamond
sparkles drifting in the upper frame, and at the end the letters loosen and
drift apart as they fade. The still gets a slow push-in behind it all.

    python3 scripts/title_intro.py bg.jpg out.mp4 \
        --line1 "another day" --line2 "at work" --duration 4.4
"""
from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "media" / "fonts"
W, H = 1080, 1920


def script_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("GreatVibes-Regular.ttf", "Allura-Regular.ttf",
                 "Sacramento-Regular.ttf", "DancingScript[wght].ttf"):
        p = FONTS / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def small_font(size: int) -> ImageFont.FreeTypeFont:
    p = FONTS / "Poppins-Medium.ttf"
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def letter_layout(text: str, font, cx: int, y: int):
    """Per-letter positions so each letter can animate on its own."""
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths)
    x = cx - total / 2
    out = []
    for ch, w in zip(text, widths):
        out.append((ch, x, y))
        x += w
    return out


def sun_doodle(size: int, label: str, alpha: float) -> Image.Image:
    """Semi-transparent circle with hand-drawn rays, tiny red label inside."""
    s = size
    im = Image.new("RGBA", (s * 2, s * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    a = int(alpha * 255)
    cx = cy = s
    r = int(s * 0.62)
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=(255, 255, 255, int(a * 0.38)),
              outline=(255, 255, 255, a), width=4)
    # rays - short strokes, hand-drawn feel via varying length
    for i in range(10):
        ang = i * math.pi / 5 + 0.25
        r0 = r + 8
        r1 = r + 8 + (14 if i % 2 else 24)
        d.line([cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
                cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)],
               fill=(255, 255, 255, a), width=5)
    f = small_font(int(s * 0.22))
    tw = f.getlength(label)
    d.text((cx - tw / 2, cy - s * 0.14), label,
           font=f, fill=(214, 84, 96, int(a * 0.9)))
    return im


def make_sparkles(rng, n: int):
    """Diamond sparkles, weighted to the upper half like the reference."""
    out = []
    for _ in range(n):
        out.append({
            "x": rng.uniform(0.03, 0.97),
            "y": rng.uniform(0.03, 0.62) ** 1.4,
            "size": rng.uniform(7, 26),
            "phase": rng.uniform(0, 2 * math.pi),
            "speed": rng.uniform(1.2, 2.8),
            "drift": rng.uniform(-6, 6),
        })
    return out


def draw_sparkle(d: ImageDraw.ImageDraw, x: float, y: float, s: float, a: int):
    d.polygon([(x, y - s), (x + s * 0.32, y), (x, y + s), (x - s * 0.32, y)],
              fill=(255, 255, 255, a))
    d.polygon([(x - s, y), (x, y + s * 0.32), (x + s, y), (x, y - s * 0.32)],
              fill=(255, 255, 255, int(a * 0.8)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Handwriting intro title clip.")
    ap.add_argument("background")
    ap.add_argument("output")
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", default="")
    ap.add_argument("--duration", type=float, default=4.4)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size1", type=int, default=210)
    ap.add_argument("--size2", type=int, default=150)
    ap.add_argument("--doodle-label", default="sun")
    ap.add_argument("--zoom", type=float, default=0.10, help="push-in over the clip")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    bg = Image.open(args.background).convert("RGB")
    if bg.size != (W, H):
        bg = bg.resize((W, H), Image.LANCZOS)
    bg_big = bg.resize((int(W * 1.25), int(H * 1.25)), Image.LANCZOS)

    f1, f2 = script_font(args.size1), script_font(args.size2)
    # Text block sits in the lower-centre band, clear of a top logo.
    cy1, cy2 = int(H * 0.585), int(H * 0.585) + int(args.size1 * 0.78)
    letters = letter_layout(args.line1, f1, W // 2 - 40, cy1)
    letters2 = letter_layout(args.line2, f2, W // 2 + 70, cy2) if args.line2 else []
    all_letters = [(l, 0) for l in letters] + [(l, 1) for l in letters2]
    n_letters = len(all_letters)

    rng = np.random.default_rng(args.seed)
    sparkles = make_sparkles(rng, 46)
    scatter = [(rng.uniform(-1, 1), rng.uniform(-1.6, -0.4), rng.uniform(-14, 14))
               for _ in range(n_letters)]

    d_total = args.duration
    write_start, write_span = 0.30, 1.7        # letters appear across this window
    hold_end = d_total - 0.9                    # then scatter through the tail
    total = int(round(d_total * args.fps))

    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", args.output],
        stdin=subprocess.PIPE)

    doodle_cache = {}
    for i in range(total):
        t = i / args.fps
        p = t / d_total

        # Slow push-in on the background.
        z = 1.0 + args.zoom * ease(p)
        cw, ch = int(W / z * 1.25), int(H / z * 1.25)
        x0 = (bg_big.width - cw) // 2
        y0 = (bg_big.height - ch) // 2
        frame = bg_big.crop((x0, y0, x0 + cw, y0 + ch)).resize((W, H), Image.LANCZOS)

        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        crisp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd, cd = ImageDraw.Draw(glow), ImageDraw.Draw(crisp)
        sd_ = ImageDraw.Draw(shadow)

        scatter_p = ease((t - hold_end) / max(0.05, d_total - hold_end)) if t > hold_end else 0.0

        for idx, ((ch_, lx, ly), which) in enumerate(all_letters):
            born = write_start + write_span * (idx / max(1, n_letters - 1))
            a = ease((t - born) / 0.30)
            if a <= 0.01:
                continue
            rise = (1 - a) * 26
            dx = dy = rot = 0.0
            if scatter_p > 0:
                sx, sy, _ = scatter[idx]
                dx = sx * 150 * scatter_p
                dy = sy * 120 * scatter_p
                a *= max(0.0, 1.0 - scatter_p * 1.15)
                if a <= 0.01:
                    continue
            font = f1 if which == 0 else f2
            alpha = int(a * 255)
            pos = (lx + dx, ly + dy - rise)
            # Soft dark shadow keeps white script legible over her white coat.
            sd_.text((pos[0] + 3, pos[1] + 5), ch_, font=font,
                     fill=(30, 22, 20, int(alpha * 0.55)))
            gd.text(pos, ch_, font=font, fill=(255, 255, 255, alpha))
            cd.text(pos, ch_, font=font, fill=(255, 255, 255, alpha))

        # Doodle rides the write-on of line 1, dies with the scatter.
        da = ease((t - (write_start + 0.5)) / 0.5) * (1.0 - scatter_p)
        if da > 0.02:
            key = round(da, 2)
            if key not in doodle_cache:
                doodle_cache[key] = sun_doodle(120, args.doodle_label, key)
            doo = doodle_cache[key]
            frame_w = f1.getlength(args.line1)
            frame.paste(doo, (int(W // 2 + frame_w / 2 - 60), int(cy1 - 60)),
                        doo)

        # Sparkles twinkle through the whole clip, thinning near the end.
        sp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sp)
        fade_all = 1.0 - ease((t - (d_total - 1.1)) / 1.1) if t > d_total - 1.1 else 1.0
        for s in sparkles:
            tw = (math.sin(s["phase"] + t * s["speed"] * 2 * math.pi / 2) + 1) / 2
            a = int(200 * (tw ** 2.2) * fade_all)
            if a < 8:
                continue
            draw_sparkle(sd, s["x"] * W + s["drift"] * t, s["y"] * H, s["size"], a)
        sp = sp.filter(ImageFilter.GaussianBlur(0.6))

        glow = glow.filter(ImageFilter.GaussianBlur(7))
        shadow = shadow.filter(ImageFilter.GaussianBlur(9))
        out = frame.convert("RGBA")
        out = Image.alpha_composite(out, sp)
        out = Image.alpha_composite(out, shadow)
        out = Image.alpha_composite(out, glow)   # halo
        out = Image.alpha_composite(out, glow)   # stronger halo
        out = Image.alpha_composite(out, crisp)
        proc.stdin.write(out.convert("RGB").tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding the intro")
    print(f"wrote {args.output}  {d_total:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
