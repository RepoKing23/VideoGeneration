#!/usr/bin/env python3
"""File raw uploads into the media library and keep a catalogue.

Originals are never modified or thrown away: they move into
`media/raw/<shoot>/`, and everything downstream works from derivatives. HEIC
stills get a JPEG sibling in the library because ffmpeg cannot decode HEIC.

    python3 scripts/organize_media.py --shoot 2026-08-23-lip-filler
    python3 scripts/organize_media.py --shoot my-shoot --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reel.util import probe  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
HEIC_EXT = {".heic", ".heif"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}


def capture_time(path: Path) -> datetime:
    """Best available capture time: EXIF, then container metadata, then mtime."""
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT | HEIC_EXT:
        try:
            import pillow_heif
            from PIL import Image
            pillow_heif.register_heif_opener()
            exif = Image.open(path).getexif()
            raw = exif.get(36867) or exif.get(306)
            if raw:
                return datetime.strptime(str(raw), "%Y:%m:%d %H:%M:%S")
        except Exception:
            pass
    else:
        try:
            import subprocess
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "format_tags=creation_time", "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True).stdout.strip()
            if out:
                return datetime.fromisoformat(out.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def convert_heic(src: Path, dst: Path) -> tuple[int, int]:
    """Write a full-quality JPEG next to the library, honouring EXIF rotation."""
    import pillow_heif
    from PIL import Image, ImageOps
    pillow_heif.register_heif_opener()
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, quality=95, subsampling=0)
    return im.size


def main() -> int:
    ap = argparse.ArgumentParser(description="Organise raw uploads into the media library.")
    ap.add_argument("--shoot", required=True,
                    help="folder name for this batch, e.g. 2026-08-23-lip-filler")
    ap.add_argument("--source", default="media/clips",
                    help="where the unsorted uploads currently sit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    source = ROOT / args.source
    raw_dir = ROOT / "media" / "raw" / args.shoot
    lib_clips = ROOT / "media" / "library" / "clips" / args.shoot
    lib_images = ROOT / "media" / "library" / "images" / args.shoot
    lib_audio = ROOT / "media" / "library" / "audio" / args.shoot

    candidates = sorted(
        p for p in source.rglob("*")
        if p.is_file() and not p.name.startswith(".")
        and p.suffix.lower() in (VIDEO_EXT | IMAGE_EXT | HEIC_EXT | AUDIO_EXT)
        and "library" not in p.parts and "raw" not in p.parts
    )
    if not candidates:
        print(f"nothing to organise in {source.relative_to(ROOT)}")
        return 0

    catalog = []
    for path in candidates:
        suffix = path.suffix.lower()
        when = capture_time(path)
        stamp = when.strftime("%Y%m%d-%H%M%S")

        if suffix in HEIC_EXT:
            kind, lib_dir, lib_name = "image", lib_images, f"{stamp}_{path.stem}.jpg"
        elif suffix in VIDEO_EXT:
            kind, lib_dir, lib_name = "clip", lib_clips, f"{stamp}_{path.stem}{suffix}"
        elif suffix in AUDIO_EXT:
            kind, lib_dir, lib_name = "audio", lib_audio, f"{stamp}_{path.stem}{suffix}"
        else:
            kind, lib_dir, lib_name = "image", lib_images, f"{stamp}_{path.stem}{suffix}"

        raw_dst = raw_dir / path.name
        lib_dst = lib_dir / lib_name
        print(f"{path.name:<20} -> raw/{args.shoot}/{path.name}")
        print(f"{'':<20}    library/{kind}s/{args.shoot}/{lib_name}")
        if args.dry_run:
            continue

        raw_dst.parent.mkdir(parents=True, exist_ok=True)
        lib_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), raw_dst)

        entry = {"kind": kind, "shoot": args.shoot,
                 "raw": str(raw_dst.relative_to(ROOT)),
                 "library": str(lib_dst.relative_to(ROOT)),
                 "captured": when.isoformat(timespec="seconds")}
        if suffix in HEIC_EXT:
            w, h = convert_heic(raw_dst, lib_dst)
            entry.update(width=w, height=h)
        else:
            shutil.copyfile(raw_dst, lib_dst)
            try:
                m = probe(lib_dst)
                entry.update(width=m["width"], height=m["height"],
                             duration=round(m["duration"], 2), has_audio=m["has_audio"])
            except RuntimeError:
                pass
        catalog.append(entry)

    if args.dry_run:
        print("\n(dry run, nothing moved)")
        return 0

    cat_path = ROOT / "media" / "catalog.json"
    existing = json.loads(cat_path.read_text()) if cat_path.exists() else []
    known = {e["library"] for e in existing}
    existing += [e for e in catalog if e["library"] not in known]
    existing.sort(key=lambda e: (e["shoot"], e["captured"]))
    cat_path.write_text(json.dumps(existing, indent=2) + "\n")
    print(f"\ncatalogued {len(catalog)} new assets -> media/catalog.json "
          f"({len(existing)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
