#!/usr/bin/env python3
"""Apply a per-photo edit recipe: straighten, crop, brighten.

Driven by a project's prep.json so every edit is written down and repeatable,
rather than being a one-off command nobody can reproduce later.

Crops are expressed as a vertical band plus a horizontal centre, and the width
is derived to hit the output aspect exactly. That means the reel engine never
has to crop further, so what you approve here is what ships.

    python3 scripts/prep_photos.py projects/<name>/prep.json
    python3 scripts/prep_photos.py projects/<name>/prep.json --sheet
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pillow_heif
from PIL import Image, ImageEnhance, ImageOps

pillow_heif.register_heif_opener()
ROOT = Path(__file__).resolve().parents[1]


def apply_gain(im: Image.Image, gain) -> Image.Image:
    """Per-channel multiplier, used to match a before/after pair.

    Shots minutes apart drift in colour, and an unmatched pair reads as a
    lighting change rather than a result.  Matching the skin means the only
    difference left on screen is the one being demonstrated.
    """
    r, g, b = im.split()
    gr, gg, gb = (float(x) for x in gain)
    r = r.point(lambda v: max(0, min(255, int(v * gr))))
    g = g.point(lambda v: max(0, min(255, int(v * gg))))
    b = b.point(lambda v: max(0, min(255, int(v * gb))))
    return Image.merge("RGB", (r, g, b))


def enhance(im: Image.Image, o: dict) -> Image.Image:
    if o.get("gain"):
        im = apply_gain(im, o["gain"])
    if o.get("brighten"):
        im = ImageEnhance.Brightness(im).enhance(1.0 + float(o["brighten"]))
    if o.get("contrast"):
        im = ImageEnhance.Contrast(im).enhance(float(o["contrast"]))
    if o.get("saturation"):
        im = ImageEnhance.Color(im).enhance(float(o["saturation"]))
    if o.get("sharpen"):
        im = ImageEnhance.Sharpness(im).enhance(1.0 + float(o["sharpen"]))
    if o.get("warmth"):
        # Lift red, ease blue - skin reads healthier without a global tint.
        w = float(o["warmth"])
        r, g, b = im.split()
        r = r.point(lambda v: min(255, int(v * (1 + 0.10 * w))))
        b = b.point(lambda v: max(0, int(v * (1 - 0.08 * w))))
        im = Image.merge("RGB", (r, g, b))
    return im


def crop_box(size: tuple[int, int], item: dict, aspect: float) -> tuple[int, int, int, int]:
    """Vertical band + horizontal centre -> an exact-aspect box, clamped in frame."""
    w, h = size
    y0 = int(round(float(item["y0"]) * h))
    y1 = int(round(float(item["y1"]) * h))
    box_h = max(1, y1 - y0)
    box_w = int(round(box_h * aspect))
    cx = int(round(float(item.get("center_x", 0.5)) * w))
    x0 = cx - box_w // 2

    # Clamp inside the frame without changing the box size, so the aspect holds.
    if box_w <= w:
        x0 = max(0, min(x0, w - box_w))
    else:
        x0, box_w = 0, w
    if box_h > h:
        y0, box_h = 0, h
    y0 = max(0, min(y0, h - box_h))
    return x0, y0, x0 + box_w, y0 + box_h


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare photos for a reel.")
    ap.add_argument("recipe")
    ap.add_argument("--sheet", action="store_true", help="also write a review contact sheet")
    args = ap.parse_args()

    recipe_path = Path(args.recipe).resolve()
    recipe = json.loads(recipe_path.read_text())
    project_dir = recipe_path.parent
    src_root = ROOT / recipe["source_root"]
    out_dir = project_dir / recipe.get("output_dir", "assets")
    out_dir.mkdir(parents=True, exist_ok=True)
    defaults = recipe.get("defaults", {})
    aspect = recipe.get("aspect", 9 / 16)

    written = []
    for item in recipe["items"]:
        src = src_root / item["src"]
        if not src.exists():
            raise FileNotFoundError(src)
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")

        angle = float(item.get("rotate", 0))
        if angle:
            # expand=False keeps the geometry predictable; we crop well inside.
            im = im.rotate(angle, resample=Image.BICUBIC, expand=False)

        im = im.crop(crop_box(im.size, item, aspect))

        opts = {**defaults, **{k: v for k, v in item.items()
                               if k in ("brighten", "contrast", "saturation",
                                        "warmth", "sharpen", "gain")}}
        im = enhance(im, opts)

        target_h = recipe.get("output_height", 1920)
        if im.height != target_h:
            im = im.resize((int(round(target_h * aspect)), target_h), Image.LANCZOS)

        dst = out_dir / item["out"]
        im.save(dst, quality=94, subsampling=0)
        written.append(dst)
        print(f"{item['src']:<34} -> {dst.relative_to(project_dir)}  "
              f"{im.width}x{im.height}  rot={angle}")

    if args.sheet and written:
        thumbs = [Image.open(p).resize((300, int(300 / aspect)), Image.LANCZOS) for p in written]
        sheet = Image.new("RGB", (300 * len(thumbs), thumbs[0].height), "black")
        for i, t in enumerate(thumbs):
            sheet.paste(t, (i * 300, 0))
        sheet_path = project_dir / "review_sheet.jpg"
        sheet.save(sheet_path, quality=90)
        print(f"\nreview sheet -> {sheet_path.relative_to(project_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
