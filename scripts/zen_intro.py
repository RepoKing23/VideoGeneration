#!/usr/bin/env python3
"""Calm, stylistic intro title over a still - the zen counterpart to
title_intro.py's sparkly handwriting look.

The recipe: the still breathes in slowly (gentle push-in) under a soft dark
veil; the script headline resolves letter by letter from a blur, each letter
rising a few pixels as it sharpens; a thin gold rule grows outward from the
centre; a small letter-spaced subline tracks slowly apart beneath it; a few
out-of-focus motes drift upward the whole time. At the end everything lifts
and dissolves together - no scatter, no sparkle.

    python3 scripts/zen_intro.py bg.jpg out.mp4 \
        --line1 "find your calm" --line2 "THE CLEO ROOM" --duration 5.2
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
GOLD = (217, 169, 78)


def script_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("Allura-Regular.ttf", "GreatVibes-Regular.ttf",
                 "Sacramento-Regular.ttf", "DancingScript[wght].ttf"):
        p = FONTS / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def light_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("Poppins-Light.ttf", "Poppins-Regular.ttf"):
        p = FONTS / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def letter_layout(text: str, font, cx: float, y: float):
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths)
    x = cx - total / 2
    out = []
    for ch, w in zip(text, widths):
        out.append((ch, x, y, w))
        x += w
    return out


def draw_blurred_letter(layer: Image.Image, ch: str, x: float, y: float,
                        font, alpha: int, blur: float,
                        fill=(255, 255, 255)) -> None:
    """Letter rendered on its own tile so it can carry its own blur while it
    resolves; pasting whole-frame blurs per letter would be far too slow."""
    pad = int(24 + blur * 4)
    bbox = font.getbbox(ch)
    tw = max(1, bbox[2] - bbox[0]) + pad * 2
    th = max(1, bbox[3] - bbox[1]) + pad * 2
    tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.text((pad - bbox[0], pad - bbox[1]), ch, font=font, fill=(*fill, alpha))
    if blur > 0.15:
        tile = tile.filter(ImageFilter.GaussianBlur(blur))
    layer.alpha_composite(tile, (int(x - pad + bbox[0]), int(y - pad + bbox[1])))


def make_motes(rng, n: int):
    """Soft bokeh motes, biased large-and-dim; they read as dust in light."""
    out = []
    for _ in range(n):
        out.append({
            "x": rng.uniform(0.05, 0.95),
            "y": rng.uniform(0.1, 1.05),
            "r": rng.uniform(5, 26),
            "alpha": rng.uniform(0.05, 0.16),
            "rise": rng.uniform(14, 40),      # px per second, upward
            "sway": rng.uniform(8, 26),
            "phase": rng.uniform(0, 2 * math.pi),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Calm zen intro title clip.")
    ap.add_argument("background")
    ap.add_argument("output")
    ap.add_argument("--line1", required=True)
    ap.add_argument("--line2", default="")
    ap.add_argument("--duration", type=float, default=5.2)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size1", type=int, default=225)
    ap.add_argument("--size2", type=int, default=46)
    ap.add_argument("--veil", type=float, default=0.34,
                    help="darkness of the veil over the still, 0..1")
    ap.add_argument("--zoom", type=float, default=0.07)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args()

    bg = Image.open(args.background).convert("RGB")
    if bg.size != (W, H):
        bg = bg.resize((W, H), Image.LANCZOS)
    bg_big = bg.resize((int(W * 1.25), int(H * 1.25)), Image.LANCZOS)

    size1 = args.size1
    f1 = script_font(size1)
    # Script faces run wide; shrink until the headline sits well inside the
    # frame rather than trusting the caller's point size.
    while size1 > 60 and f1.getlength(args.line1) > W * 0.86:
        size1 -= 6
        f1 = script_font(size1)
    f2 = light_font(args.size2)
    sub = " ".join(args.line2.upper()) if args.line2 else ""

    cy1 = int(H * 0.44)
    rule_y = int(cy1 + size1 * 1.06)
    cy2 = rule_y + 46

    letters = letter_layout(args.line1, f1, W / 2, cy1)
    n_letters = len([l for l in letters if l[0].strip()])

    rng = np.random.default_rng(args.seed)
    motes = make_motes(rng, 14)

    d_total = args.duration
    write_start, write_span = 0.55, 2.0     # headline resolves across this
    resolve = 0.85                          # per-letter blur-to-sharp time
    rule_start = write_start + write_span * 0.55
    sub_start = rule_start + 0.35
    lift_start = d_total - 1.0              # everything rises and dissolves
    total = int(round(d_total * args.fps))

    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
         "-pix_fmt", "yuv420p", args.output],
        stdin=subprocess.PIPE)

    veil = Image.new("RGBA", (W, H), (12, 10, 9, int(args.veil * 255)))

    for i in range(total):
        t = i / args.fps
        p = t / d_total

        z = 1.0 + args.zoom * ease(p)
        cw, ch_ = int(W / z * 1.25), int(H / z * 1.25)
        x0 = (bg_big.width - cw) // 2
        y0 = (bg_big.height - ch_) // 2
        frame = bg_big.crop((x0, y0, x0 + cw, y0 + ch_)).resize((W, H), Image.LANCZOS)
        out = frame.convert("RGBA")
        out.alpha_composite(veil)

        # Motes drift up behind the text, breathing in brightness.
        mote_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        md = ImageDraw.Draw(mote_layer)
        for m in motes:
            my = (m["y"] * H - m["rise"] * t) % (H * 1.1) - H * 0.05
            mx = m["x"] * W + math.sin(m["phase"] + t * 0.5) * m["sway"]
            tw_ = 0.75 + 0.25 * math.sin(m["phase"] * 2 + t * 0.8)
            a = int(m["alpha"] * tw_ * 255)
            r = m["r"]
            md.ellipse([mx - r, my - r, mx + r, my + r], fill=(255, 246, 228, a))
        mote_layer = mote_layer.filter(ImageFilter.GaussianBlur(6))
        out.alpha_composite(mote_layer)

        lift_p = ease((t - lift_start) / max(0.05, d_total - lift_start)) if t > lift_start else 0.0
        lift_dy = -34 * lift_p
        lift_a = 1.0 - lift_p

        text_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # Headline: letters resolve from blur, in order, each rising softly.
        li = 0
        for ch, lx, ly, _w in letters:
            if not ch.strip():
                li += 0  # spaces neither animate nor advance the stagger
                continue
            born = write_start + write_span * (li / max(1, n_letters - 1))
            li += 1
            a = ease_out((t - born) / resolve)
            if a <= 0.01:
                continue
            alpha = int(a * 255 * lift_a)
            if alpha <= 2:
                continue
            blur = (1 - a) * 7.0
            rise = (1 - a) * 18
            draw_blurred_letter(text_layer, ch, lx, ly - rise + lift_dy, f1,
                                alpha, blur)
            if 0.05 < a < 0.999:
                # A soft warm halo only while the letter is resolving, so the
                # settle reads as light dimming to stillness.
                draw_blurred_letter(glow_layer, ch, lx, ly - rise + lift_dy, f1,
                                    int(alpha * 0.55), max(blur, 5.0),
                                    fill=(255, 233, 196))

        # Gold rule grows outward from the centre.
        ra = ease_out((t - rule_start) / 0.9)
        if ra > 0.01:
            half = ra * 150
            rd = ImageDraw.Draw(text_layer)
            y = rule_y + lift_dy
            rd.line([W / 2 - half, y, W / 2 + half, y],
                    fill=(*GOLD, int(230 * lift_a)), width=3)
            dot_a = int(230 * ease((ra - 0.8) / 0.2) * lift_a)
            if dot_a > 0:
                for sx in (-1, 1):
                    x = W / 2 + sx * (half + 14)
                    rd.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(*GOLD, dot_a))

        # Subline fades up as one piece while its tracking eases wider.
        sa = ease((t - sub_start) / 1.1)
        if sub and sa > 0.01:
            spread = 0.86 + 0.14 * ease_out((t - sub_start) / 2.2)
            widths = [f2.getlength(c) for c in sub]
            gaps = [w * spread for w in widths]
            x = W / 2 - sum(gaps) / 2
            alpha = int(sa * 235 * lift_a)
            sd = ImageDraw.Draw(text_layer)
            for c, g in zip(sub, gaps):
                sd.text((x, cy2 + (1 - sa) * 12 + lift_dy), c, font=f2,
                        fill=(244, 240, 233, alpha))
                x += g

        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(9))
        shadow = text_layer.filter(ImageFilter.GaussianBlur(8))
        shadow_px = np.array(shadow)
        shadow_px[..., :3] = (26, 20, 16)
        shadow_px[..., 3] = (shadow_px[..., 3] * 0.6).astype(np.uint8)
        out.alpha_composite(Image.fromarray(shadow_px, "RGBA"), (2, 5))
        out.alpha_composite(glow_layer)
        out.alpha_composite(text_layer)
        proc.stdin.write(out.convert("RGB").tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding the intro")
    print(f"wrote {args.output}  {d_total:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
