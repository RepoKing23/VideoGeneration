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
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

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


_REMBG_SESSION = None


def matte_black(im: Image.Image, opts: dict) -> Image.Image:
    """Cut the subject out and composite over solid black.

    Uses rembg (u2net). The alpha it returns is already soft at the edges;
    an optional extra feather softens hairlines further. Falls back to a
    brightness/saturation matte if rembg is unavailable - the walls behind
    these photos are bright and grey, the subject is warm skin and dark hair.
    """
    global _REMBG_SESSION
    try:
        from rembg import remove, new_session
        if _REMBG_SESSION is None:
            _REMBG_SESSION = new_session(opts.get("model", "u2net"))
        rgba = remove(im, session=_REMBG_SESSION)
    except Exception as exc:                       # noqa: BLE001
        print(f"  rembg unavailable ({exc}); using brightness matte")
        rgba = _brightness_matte(im, opts)

    alpha = rgba.split()[3]
    feather = int(opts.get("feather", 0))
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    black = Image.new("RGB", im.size, (0, 0, 0))
    black.paste(rgba.convert("RGB"), (0, 0), alpha)
    return black


def _brightness_matte(im: Image.Image, opts: dict) -> Image.Image:
    """Background = bright AND low-saturation pixels; subject keeps alpha."""
    import numpy as np
    hsv = np.asarray(im.convert("HSV"), dtype=np.int16)
    lum = np.asarray(im.convert("L"), dtype=np.int16)
    bg = (lum > int(opts.get("lum", 175))) & (hsv[..., 1] < int(opts.get("sat", 40)))
    alpha = Image.fromarray(((~bg) * 255).astype("uint8"), "L")
    alpha = alpha.filter(ImageFilter.MedianFilter(9))
    alpha = alpha.filter(ImageFilter.GaussianBlur(int(opts.get("feather", 12))))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out


def censor_region(im: Image.Image, c: dict) -> Image.Image:
    """Blur a rect of the photo (fractions of its size) beyond recognition.

    Runs at full source resolution before any scaling, so the radius stays
    genuinely heavy in the output. The blur is composited through a feathered
    rounded-rect mask so the strip melts into the photo instead of seaming.
    """
    w, h = im.size
    x0, y0 = int(w * float(c.get("x0", 0.0))), int(h * float(c["y0"]))
    x1, y1 = int(w * float(c.get("x1", 1.0))), int(h * float(c["y1"]))
    radius = int(c.get("blur", 60))

    blurred = im.filter(ImageFilter.GaussianBlur(radius))
    # A second pass makes the region unrecoverable even at this radius.
    blurred = blurred.filter(ImageFilter.GaussianBlur(radius // 2))

    # The declared rect is the guaranteed-censored core: the feather (and the
    # rounded corners) live OUTSIDE it, padded further wherever the rect meets
    # the photo edge. Feathering inward would leave a half-blended strip of
    # recognisable detail just inside the band.
    feather = max(6, (y1 - y0) // 10)
    pad = feather * 2
    ex0 = x0 - pad if x0 <= 2 else x0
    ex1 = x1 + pad if x1 >= w - 2 else x1
    ey0 = y0 - pad if y0 <= 2 else y0
    ey1 = y1 + pad if y1 >= h - 2 else y1 + pad

    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    corner = max(8, (y1 - y0) // 4)
    d.rounded_rectangle([ex0, ey0, ex1, ey1], radius=corner, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather))

    return Image.composite(blurred, im, mask)


def canvas_place(im: Image.Image, width: int, height: int, item: dict,
                 margin: int) -> Image.Image:
    """Fit the whole photo onto a black canvas, letterbox style.

    `canvas_scale`/`canvas_dx`/`canvas_dy` nudge the placement, which is what
    lets a before/after pair line up for the split slider without cropping
    either photo.
    """
    scale = min((width - 2 * margin) / im.width,
                (height - 2 * margin) / im.height)
    scale *= float(item.get("canvas_scale", 1.0))
    nw, nh = int(round(im.width * scale)), int(round(im.height * scale))
    photo = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    x = (width - nw) // 2 + int(item.get("canvas_dx", 0))
    y = (height - nh) // 2 + int(item.get("canvas_dy", 0))
    canvas.paste(photo, (x, y))
    return canvas


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
        if angle and (item.get("canvas") or recipe.get("canvas")):
            # In canvas mode nothing is cropped away later, so trim the wedge
            # of empty corner the rotation itself introduced.
            trim = min(0.06, abs(angle) * 0.009)
            w0, h0 = im.size
            im = im.crop((int(w0 * trim), int(h0 * trim),
                          int(w0 * (1 - trim)), int(h0 * (1 - trim))))

        matte = item.get("matte", recipe.get("matte"))
        if matte:
            im = matte_black(im, matte if isinstance(matte, dict) else {})

        target_h = recipe.get("output_height", 1920)
        canvas_mode = bool(item.get("canvas") or recipe.get("canvas"))
        if not canvas_mode:
            im = im.crop(crop_box(im.size, item, aspect))

        opts = {**defaults, **{k: v for k, v in item.items()
                               if k in ("brighten", "contrast", "saturation",
                                        "warmth", "sharpen", "gain")}}
        im = enhance(im, opts)

        # Censor after enhancement: sharpening must never run over the blur,
        # or it re-introduces exactly the edges the blur removed.
        if item.get("censor"):
            im = censor_region(im, item["censor"])

        if canvas_mode:
            im = canvas_place(im, int(round(target_h * aspect)), target_h,
                              item, int(recipe.get("canvas_margin", 40)))
        elif im.height != target_h:
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
