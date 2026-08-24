"""Shared helpers: colours, timing, ffmpeg/ffprobe wrappers."""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    """Run a command, raising with captured stderr when it fails."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write("\n$ " + " ".join(shlex.quote(c) for c in cmd) + "\n")
        sys.stderr.write(proc.stderr[-4000:] + "\n")
        raise RuntimeError(f"command failed ({proc.returncode}): {cmd[0]}")
    if not quiet:
        sys.stderr.write(proc.stderr[-2000:])
    return proc


def ffmpeg(args: list[str], quiet: bool = True) -> None:
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], quiet=quiet)


def probe(path: str | Path) -> dict:
    """Return {duration, width, height, fps, has_audio} for a media file."""
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    fps = 0.0
    if video and video.get("r_frame_rate", "0/0") != "0/0":
        num, _, den = video["r_frame_rate"].partition("/")
        fps = float(num) / float(den or 1)
    if not duration and video and video.get("duration"):
        duration = float(video["duration"])
    return {
        "path": str(path),
        "duration": duration,
        "width": int(video["width"]) if video else 0,
        "height": int(video["height"]) if video else 0,
        "fps": round(fps, 3),
        "has_audio": audio is not None,
        "is_image": bool(video) and duration == 0.0,
    }


def hex_to_ass(colour: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (ASS is BGR with an alpha prefix, 0 = opaque)."""
    c = colour.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"bad colour {colour!r}, expected #RRGGBB")
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def hex_to_tag(colour: str, alpha: int = 0) -> str:
    """Colour for use inside an override block, which needs a terminating &."""
    return hex_to_ass(colour, alpha) + "&"


def ass_time(seconds: float) -> str:
    """Seconds -> ASS H:MM:SS.cc timestamp."""
    seconds = max(0.0, seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def escape_filter_path(path: str | Path) -> str:
    """Escape a path for use inside an ffmpeg filter argument."""
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
