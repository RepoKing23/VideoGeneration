#!/usr/bin/env python3
"""Animated outro CTA with logo, gold accents and elegant typography.

Uses the clinic image as a soft blurred background, overlays the logo with
a scale-fade animation, adds gold decorative rules, and animates CTA text.
Matches the zen intro aesthetic.

    python3 scripts/zen_outro.py bg.jpg logo.png out.mp4 \
        --cta "book your visit" --duration 4.5
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
CREAM = (252, 249, 244)
WARM_WHITE = (248, 245, 240)


def script_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("Allura-Regular.ttf", "GreatVibes-Regular.ttf"):
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


def semibold_font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("Poppins-SemiBold.ttf", "Poppins-Regular.ttf"):
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


def ease_out_back(t: float) -> float:
    """Slight overshoot for a luxurious settle."""
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def load_logo(path: str, target_width: int) -> Image.Image:
    """Load logo and convert white bg to transparency."""
    logo = Image.open(path).convert("RGBA")
    px = np.array(logo)
    # White bg -> transparent: where all RGB > 240, set alpha to 0
    white_mask = (px[..., 0] > 240) & (px[..., 1] > 240) & (px[..., 2] > 240)
    # Soft edge: near-white gets partial transparency
    near_white = (px[..., 0] > 200) & (px[..., 1] > 200) & (px[..., 2] > 200) & ~white_mask
    px[white_mask, 3] = 0
    brightness = px[near_white, :3].mean(axis=1) if near_white.any() else np.array([])
    if len(brightness) > 0:
        px[near_white, 3] = (255 - (brightness - 200) * (255 / 55)).clip(0, 255).astype(np.uint8)
    logo = Image.fromarray(px, "RGBA")
    # Resize to target width keeping aspect
    ratio = target_width / logo.width
    logo = logo.resize((target_width, int(logo.height * ratio)), Image.LANCZOS)
    return logo


def make_motes(rng, n: int):
    out = []
    for _ in range(n):
        out.append({
            "x": rng.uniform(0.05, 0.95),
            "y": rng.uniform(0.1, 1.05),
            "r": rng.uniform(4, 18),
            "alpha": rng.uniform(0.04, 0.10),
            "rise": rng.uniform(10, 30),
            "sway": rng.uniform(6, 20),
            "phase": rng.uniform(0, 2 * math.pi),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Animated zen outro CTA.")
    ap.add_argument("background")
    ap.add_argument("logo")
    ap.add_argument("output")
    ap.add_argument("--cta", default="book your visit")
    ap.add_argument("--subtext", default="")
    ap.add_argument("--duration", type=float, default=4.5)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--logo-width", type=int, default=340)
    ap.add_argument("--veil", type=float, default=0.82,
                    help="lightness of the cream overlay, 0..1")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    # Background: heavily blurred and lightened clinic image
    bg = Image.open(args.background).convert("RGB")
    if bg.size != (W, H):
        bg = bg.resize((W, H), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(35))
    # Warm cream tint overlay
    bg_arr = np.array(bg, dtype=np.float32)
    cream_arr = np.array(CREAM, dtype=np.float32)
    bg_arr = bg_arr * (1 - args.veil) + cream_arr * args.veil
    bg_arr = bg_arr.clip(0, 255).astype(np.uint8)
    bg = Image.fromarray(bg_arr)

    logo = load_logo(args.logo, args.logo_width)
    logo_cx, logo_cy = W // 2, int(H * 0.38)

    cta_font = script_font(82)
    cta_text = args.cta
    # Auto-size if needed
    while cta_font.getlength(cta_text) > W * 0.80 and cta_font.size > 40:
        cta_font = script_font(cta_font.size - 4)

    sub_font = light_font(32)
    sub_text = " ".join(args.subtext.upper()) if args.subtext else ""

    rng = np.random.default_rng(args.seed)
    motes = make_motes(rng, 10)

    d = args.duration
    logo_start = 0.3
    logo_dur = 0.9
    rule_start = logo_start + 0.6
    cta_start = rule_start + 0.3
    sub_start = cta_start + 0.4
    fade_out_start = d - 0.9

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

        frame = bg.copy().convert("RGBA")

        # Subtle gold motes for continuity with intro
        mote_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        md = ImageDraw.Draw(mote_layer)
        for m in motes:
            my = (m["y"] * H - m["rise"] * t) % (H * 1.1) - H * 0.05
            mx = m["x"] * W + math.sin(m["phase"] + t * 0.4) * m["sway"]
            tw_ = 0.75 + 0.25 * math.sin(m["phase"] * 2 + t * 0.6)
            a = int(m["alpha"] * tw_ * 255)
            r = m["r"]
            md.ellipse([mx - r, my - r, mx + r, my + r],
                       fill=(GOLD[0], GOLD[1], GOLD[2], a))
        mote_layer = mote_layer.filter(ImageFilter.GaussianBlur(5))
        frame.alpha_composite(mote_layer)

        # Fade out
        fade_out = 1.0
        if t > fade_out_start:
            fade_out = 1.0 - ease((t - fade_out_start) / (d - fade_out_start))

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Logo: scale up from 85% with slight overshoot, fade in
        la = ease_out((t - logo_start) / logo_dur) if t > logo_start else 0.0
        if la > 0.01:
            scale = 0.85 + 0.15 * ease_out_back(min(1.0, la / 0.8))
            alpha_logo = int(la * 255 * fade_out)
            lw = int(logo.width * scale)
            lh = int(logo.height * scale)
            if lw > 0 and lh > 0:
                scaled = logo.resize((lw, lh), Image.LANCZOS)
                # Apply alpha
                px = np.array(scaled)
                px[..., 3] = (px[..., 3].astype(np.float32) * alpha_logo / 255).clip(0, 255).astype(np.uint8)
                scaled = Image.fromarray(px, "RGBA")
                lx = logo_cx - lw // 2
                ly = logo_cy - lh // 2
                overlay.alpha_composite(scaled, (lx, ly))

        # Gold decorative rules — thin lines above and below the CTA area
        rule_y_top = int(H * 0.52)
        rule_y_bot = int(H * 0.68)
        ra = ease_out((t - rule_start) / 0.8) if t > rule_start else 0.0
        if ra > 0.01:
            half = ra * 180
            rule_alpha = int(200 * ra * fade_out)
            # Top rule with diamond ends
            draw.line([W // 2 - half, rule_y_top, W // 2 + half, rule_y_top],
                      fill=(*GOLD, rule_alpha), width=2)
            # Bottom rule
            draw.line([W // 2 - half, rule_y_bot, W // 2 + half, rule_y_bot],
                      fill=(*GOLD, rule_alpha), width=2)
            # Small diamond accents at rule ends
            diamond_a = int(200 * ease((ra - 0.7) / 0.3) * fade_out)
            if diamond_a > 0:
                for rule_y in (rule_y_top, rule_y_bot):
                    for sx in (-1, 1):
                        cx = W // 2 + sx * int(half + 10)
                        s = 5
                        draw.polygon([(cx, rule_y - s), (cx + s, rule_y),
                                      (cx, rule_y + s), (cx - s, rule_y)],
                                     fill=(*GOLD, diamond_a))

        # CTA text — elegant script in gold
        ca = ease((t - cta_start) / 0.9) if t > cta_start else 0.0
        if ca > 0.01:
            cta_y = int(H * 0.57) + int((1 - ca) * 15)
            alpha_cta = int(ca * 255 * fade_out)
            bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
            tw = bbox[2] - bbox[0]
            tx = W // 2 - tw // 2
            # Soft shadow
            draw.text((tx + 2, cta_y + 3), cta_text, font=cta_font,
                      fill=(180, 160, 130, int(alpha_cta * 0.3)))
            draw.text((tx, cta_y), cta_text, font=cta_font,
                      fill=(*GOLD, alpha_cta))

        # Subtext below CTA
        if sub_text:
            sa = ease((t - sub_start) / 0.8) if t > sub_start else 0.0
            if sa > 0.01:
                sub_y = int(H * 0.64) + int((1 - sa) * 10)
                alpha_sub = int(sa * 220 * fade_out)
                bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
                tw = bbox[2] - bbox[0]
                tx = W // 2 - tw // 2
                draw.text((tx, sub_y), sub_text, font=sub_font,
                          fill=(90, 80, 70, alpha_sub))

        frame.alpha_composite(overlay)
        proc.stdin.write(frame.convert("RGB").tobytes())

    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding the outro")
    print(f"wrote {args.output}  {d:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
