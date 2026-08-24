#!/usr/bin/env python3
"""Render a sampler showing every caption preset, for picking a look.

Uses generated gradient backgrounds rather than real footage so the type is
what you are judging.  Pass --font/--accent to preview a different treatment.

    python3 scripts/style_sampler.py --font Anton --accent "#FFE600"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reel import config, render as renderer  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

DEMOS = [
    ("word_pop",     "One word at a time",         ["one"],      "push_in"),
    ("stack_reveal", "Words stack up as you speak", ["stack"],   "pan_right"),
    ("karaoke_line", "The line lights up on beat",  ["lights"],  "ken_burns"),
    ("slide_up",     "Clean rise into place",       ["clean"],   "pull_out"),
    ("typewriter",   "Typed out for suspense",      ["suspense"], "pan_left"),
    ("bounce",       "Drops in with energy",        ["energy"],  "push_in"),
]
GRADIENTS = [
    ("0x1B1B3A", "0x3B1C57"), ("0x0F2027", "0x2C5364"), ("0x2B1B17", "0x8E3200"),
    ("0x102A43", "0x1F6F8B"), ("0x1A0F1F", "0x6D214F"), ("0x0B3D2E", "0x1E6F5C"),
]
TRANSITIONS = ["cut", "fade", "slideleft", "dissolve", "wipeup", "circleopen"]


def make_backgrounds(work: Path, seconds: float) -> list[Path]:
    work.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, (c0, c1) in enumerate(GRADIENTS):
        dst = work / f"bg{i + 1}.mp4"
        if not dst.exists():
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i",
                f"gradients=s=1080x1920:c0={c0}:c1={c1}:nb_colors=2"
                f":x0=200:y0=100:x1=900:y1=1800:speed=0.008"
                f":duration={seconds}:rate=30",
                "-vf", "noise=alls=7:allf=t+u,eq=saturation=1.05",
                "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                "-t", str(seconds), str(dst),
            ], check=True)
        paths.append(dst)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the caption style sampler.")
    ap.add_argument("--font", default="Anton")
    ap.add_argument("--accent", default="#FFE600")
    ap.add_argument("--primary", default="#FFFFFF")
    ap.add_argument("--hold", type=float, default=3.2, help="seconds per preset")
    args = ap.parse_args()

    work = ROOT / "work" / "sampler"
    make_backgrounds(work / "bg", args.hold)

    scenes = []
    for i, (preset, text, accent, motion) in enumerate(DEMOS):
        scene = {
            "src": f"work/sampler/bg/bg{i + 1}.mp4",
            "duration": args.hold,
            "fit": "cover",
            "motion": motion,
            "intensity": 0.7,
            "captions": [
                {"text": preset.replace("_", " "), "start": 0.15,
                 "end": args.hold - 0.2, "preset": "slide_up", "position": "top"},
                {"text": text, "start": 0.35, "end": args.hold - 0.2,
                 "preset": preset, "accent_words": accent},
            ],
        }
        if i:
            scene["transition"] = {"type": TRANSITIONS[i], "duration": 0.35}
        scenes.append(scene)

    project_file = work / "project.json"
    project_file.write_text(json.dumps({
        "name": "caption_sampler",
        "output": {"width": 1080, "height": 1920, "fps": 30,
                   "file": "caption_sampler.mp4", "crf": 20, "preset": "medium"},
        "style": {"font": args.font, "caption_preset": "word_pop", "size": 126,
                  "primary": args.primary, "accent": args.accent, "outline": 7,
                  "position": "center_low", "max_chars_per_line": 15},
        "grade": {"contrast": 1.04, "saturation": 1.08, "vignette": True,
                  "fade_in": 0.3, "fade_out": 0.5},
        "watermark": {"text": "caption styles", "position": "bottom",
                      "opacity": 0.45, "size": 34},
        "scenes": scenes,
    }, indent=2) + "\n")

    renderer.render(config.load(project_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
