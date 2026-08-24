#!/usr/bin/env python3
"""Turn a folder of media plus a caption script into a project.json.

    python3 scripts/new_project.py --name launch \
        --media media --captions projects/launch/captions.txt --duration 30

The caption file is one line per on-screen caption.  Blank lines are ignored.
A line starting with '#' is a comment.  Captions are spread across the scenes
in order, weighted by how long each scene runs, which gives a sane first cut
that we then hand-tune.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reel.render import IMAGE_EXT  # noqa: E402
from reel.util import probe  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

# Cycled so consecutive scenes never share a camera move.
MOTION_CYCLE = ["push_in", "pan_right", "pull_out", "ken_burns", "pan_left", "push_in", "pan_up"]
TRANSITION_CYCLE = ["fade", "slideleft", "fade", "wipeup", "dissolve", "fade", "slideright"]


def read_captions(path: Path | None) -> list[str]:
    if not path or not path.exists():
        return []
    lines = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Scaffold a reel project from a media folder.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--media", default="media", help="folder to pull clips and images from")
    ap.add_argument("--captions", help="text file, one caption per line")
    ap.add_argument("--duration", type=float, help="target total length in seconds")
    ap.add_argument("--music", help="path to a music track")
    ap.add_argument("--preset", default="word_pop", help="caption animation preset")
    ap.add_argument("--font", default="Anton")
    ap.add_argument("--accent", default="#FFE600")
    ap.add_argument("--handle", help="watermark text, e.g. @yourhandle")
    ap.add_argument("--max-clip", type=float, default=4.0,
                    help="longest a single scene may run (seconds)")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    media_root = (root / args.media) if not Path(args.media).is_absolute() else Path(args.media)
    sources = sorted(
        p for p in media_root.rglob("*")
        if p.is_file() and p.suffix.lower() in (VIDEO_EXT | IMAGE_EXT)
        and not p.name.startswith(".")
    )
    if not sources:
        print(f"no clips or images found in {media_root}", file=sys.stderr)
        return 1

    # Work out a duration for each scene.
    scenes_raw: list[dict] = []
    for path in sources:
        is_image = path.suffix.lower() in IMAGE_EXT
        if is_image:
            length = 2.6
        else:
            try:
                length = min(probe(path)["duration"], args.max_clip)
            except RuntimeError:
                print(f"skipping unreadable file: {path.name}", file=sys.stderr)
                continue
            length = max(1.2, length)
        scenes_raw.append({"path": path, "duration": round(length, 2), "is_image": is_image})

    # Scale everything to hit the requested total.
    if args.duration:
        current = sum(s["duration"] for s in scenes_raw)
        factor = args.duration / current if current else 1.0
        for s in scenes_raw:
            s["duration"] = round(max(1.0, s["duration"] * factor), 2)

    captions = read_captions(Path(args.captions) if args.captions else None)

    # Hand captions out to scenes proportionally to scene length.
    total = sum(s["duration"] for s in scenes_raw)
    per_scene: list[list[str]] = [[] for _ in scenes_raw]
    if captions:
        cursor = 0
        for i, s in enumerate(scenes_raw):
            share = s["duration"] / total if total else 0
            take = max(1, round(len(captions) * share)) if i < len(scenes_raw) - 1 else len(captions) - cursor
            take = max(0, min(take, len(captions) - cursor))
            per_scene[i] = captions[cursor:cursor + take]
            cursor += take
        if cursor < len(captions):           # anything left over rides on the last scene
            per_scene[-1].extend(captions[cursor:])

    scenes = []
    for i, s in enumerate(scenes_raw):
        rel = s["path"].relative_to(root)
        caps = []
        if per_scene[i]:
            # Leave a beat at the head and tail of the scene.
            usable_start, usable_end = 0.15, s["duration"] - 0.15
            span = max(0.4, usable_end - usable_start)
            slot = span / len(per_scene[i])
            for j, text in enumerate(per_scene[i]):
                caps.append({
                    "text": text,
                    "start": round(usable_start + j * slot, 2),
                    "end": round(usable_start + (j + 1) * slot, 2),
                })
        scene = {
            "src": str(rel),
            "duration": s["duration"],
            "fit": "cover",
            "motion": MOTION_CYCLE[i % len(MOTION_CYCLE)],
        }
        if not s["is_image"]:
            scene["start"] = 0.0
        if i > 0:
            scene["transition"] = {
                "type": TRANSITION_CYCLE[i % len(TRANSITION_CYCLE)],
                "duration": 0.35,
            }
        if caps:
            scene["captions"] = caps
        scenes.append(scene)

    project = {
        "name": args.name,
        "output": {"width": 1080, "height": 1920, "fps": 30,
                   "file": f"out/{args.name}.mp4", "crf": 19, "preset": "medium"},
        "style": {
            "font": args.font,
            "caption_preset": args.preset,
            "size": 130,
            "primary": "#FFFFFF",
            "accent": args.accent,
            "outline": 7,
            "position": "center_low",
            "uppercase": True,
            "max_chars_per_line": 16,
        },
        "grade": {"contrast": 1.05, "saturation": 1.10, "warmth": 0.3,
                  "vignette": True, "fade_in": 0.25, "fade_out": 0.5},
        "audio": {"music_gain_db": -9, "fade_in": 0.4, "fade_out": 1.2},
        "scenes": scenes,
    }
    if args.music:
        project["audio"]["music"] = args.music
    if args.handle:
        project["watermark"] = {"text": args.handle, "position": "bottom",
                                "opacity": 0.5, "size": 36}

    out_dir = root / "projects" / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "project.json"
    out_file.write_text(json.dumps(project, indent=2) + "\n")

    print(f"wrote {out_file.relative_to(root)}")
    print(f"  {len(scenes)} scenes, {sum(s['duration'] for s in scenes_raw):.1f}s, "
          f"{len(captions)} captions ({args.preset})")
    print(f"\nnext:  python3 src/build_reel.py {out_file.relative_to(root)} --preview")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
