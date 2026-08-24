#!/usr/bin/env python3
"""Render an Instagram reel from a project file.

    python3 src/build_reel.py projects/<name>/project.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from reel import config, render as renderer  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Render an Instagram reel.")
    ap.add_argument("project", help="path to project.json")
    ap.add_argument("-o", "--output", help="override the output file")
    ap.add_argument("--preview", action="store_true",
                    help="fast, lower-quality render for checking the edit")
    args = ap.parse_args()

    project = config.load(args.project)
    if args.output:
        project.out_file = args.output
    if args.preview:
        project.crf = 28
        project.x264_preset = "veryfast"
        stem = Path(project.out_file)
        project.out_file = str(stem.with_name(f"{stem.stem}_preview{stem.suffix}"))

    try:
        renderer.render(project)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
