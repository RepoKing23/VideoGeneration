#!/usr/bin/env python3
"""Turn a logo supplied as flat art on white into overlay-ready PNGs.

Brand marks usually arrive as dark artwork on a solid white background with no
alpha. Deriving alpha as a straight `255 - luminance` looks right but renders
the mark at half strength: a mid-grey anti-aliased stroke becomes a half-
transparent pixel, so thin lettering washes out to near-invisible over footage.

Instead the alpha is remapped so anything that is clearly ink becomes fully
opaque, leaving only the true edge pixels partially transparent, and the colour
is replaced with a solid fill so the mark reads as one consistent tone.

    python3 scripts/prepare_logo.py "logo.png" --name cleo-logo
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def build(src: Path, fill: tuple[int, int, int], solid_at: float,
          fade_below: float) -> Image.Image:
    im = Image.open(src).convert("RGB")
    lum = np.asarray(im.convert("L"), dtype=float)

    raw = (255.0 - lum)
    peak = raw.max() or 1.0
    a = raw / peak                                  # 0 = paper, 1 = darkest ink

    # Everything at or above `solid_at` becomes fully opaque; below
    # `fade_below` disappears. Between them is the anti-aliased edge.
    a = (a - fade_below) / max(1e-6, solid_at - fade_below)
    a = np.clip(a, 0.0, 1.0)

    alpha = Image.fromarray((a * 255).astype(np.uint8), "L")
    flat = Image.new("RGB", im.size, fill)
    out = flat.convert("RGBA")
    out.putalpha(alpha)

    bbox = alpha.point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox:
        pad = 8
        out = out.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                        min(out.width, bbox[2] + pad), min(out.height, bbox[3] + pad)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare a logo for overlay.")
    ap.add_argument("source")
    ap.add_argument("--name", required=True, help="output stem, e.g. cleo-logo")
    ap.add_argument("--dark", default="#2A2422")
    ap.add_argument("--light", default="#FFFFFF")
    ap.add_argument("--solid-at", type=float, default=0.50,
                    help="ink darkness (0-1) that should render fully opaque")
    ap.add_argument("--fade-below", type=float, default=0.08)
    args = ap.parse_args()

    out_dir = ROOT / "media" / "logo"
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Path(args.source)

    for suffix, hexcol in (("dark", args.dark), ("white", args.light)):
        rgb = tuple(int(hexcol.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        img = build(src, rgb, args.solid_at, args.fade_below)
        dst = out_dir / f"{args.name}-{suffix}.png"
        img.save(dst)
        a = np.asarray(img.split()[3], float)
        print(f"{dst.name}: {img.size}  opaque px {(a > 250).sum()}  "
              f"mean alpha where visible {a[a > 10].mean():.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
