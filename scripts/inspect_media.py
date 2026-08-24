#!/usr/bin/env python3
"""Report on everything in a media folder, so we know what we are working with.

    python3 scripts/inspect_media.py media
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reel.render import IMAGE_EXT  # noqa: E402
from reel.util import probe  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg"}


def orientation(w: int, h: int) -> str:
    if h > w * 1.2:
        return "vertical"
    if w > h * 1.2:
        return "landscape"
    return "square"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "media")
    if not root.exists():
        print(f"no such folder: {root}")
        return 1

    files = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))
    videos = [p for p in files if p.suffix.lower() in VIDEO_EXT]
    images = [p for p in files if p.suffix.lower() in IMAGE_EXT]
    audio = [p for p in files if p.suffix.lower() in AUDIO_EXT]
    other = [p for p in files if p not in videos + images + audio]

    total_footage = 0.0
    if videos:
        print(f"\nCLIPS ({len(videos)})")
        for p in videos:
            try:
                m = probe(p)
            except RuntimeError:
                print(f"  {p.name:<38} UNREADABLE")
                continue
            total_footage += m["duration"]
            print(f"  {p.name:<38} {m['width']}x{m['height']:<6} "
                  f"{orientation(m['width'], m['height']):<10} "
                  f"{m['duration']:>6.1f}s {m['fps']:>5.1f}fps "
                  f"{'audio' if m['has_audio'] else 'silent'}")

    if images:
        print(f"\nIMAGES ({len(images)})")
        for p in images:
            try:
                m = probe(p)
            except RuntimeError:
                print(f"  {p.name:<38} UNREADABLE")
                continue
            print(f"  {p.name:<38} {m['width']}x{m['height']:<6} "
                  f"{orientation(m['width'], m['height'])}")

    if audio:
        print(f"\nAUDIO ({len(audio)})")
        for p in audio:
            try:
                m = probe(p)
            except RuntimeError:
                print(f"  {p.name:<38} UNREADABLE")
                continue
            print(f"  {p.name:<38} {m['duration']:>6.1f}s")

    if other:
        print(f"\nOTHER ({len(other)})")
        for p in other:
            print(f"  {p.relative_to(root)}")

    print(f"\nTOTAL: {len(videos)} clips ({total_footage:.1f}s of footage), "
          f"{len(images)} images, {len(audio)} audio")
    if not files:
        print("  (folder is empty - drop your clips and images in here)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
