"""Camera-move presets.

Every scene is first normalised onto a supersampled canvas, then `zoompan`
crops a moving window out of it.  Working from a larger canvas is what keeps
the movement smooth instead of stepping a pixel at a time.
"""
from __future__ import annotations

SUPERSAMPLE = 2  # canvas is this many times the output size

MOTIONS = (
    "static",
    "push_in",
    "pull_out",
    "pan_left",
    "pan_right",
    "pan_up",
    "pan_down",
    "ken_burns",
)


def zoompan_chain(motion: str, width: int, height: int, frames: int, fps: int,
                  intensity: float = 1.0) -> str:
    """Build a zoompan filter string for the given motion over `frames`."""
    if motion not in MOTIONS:
        raise ValueError(f"unknown motion {motion!r}; choose from {', '.join(MOTIONS)}")
    frames = max(1, int(frames))
    # `p` is progress 0..1 across the scene, expressed in output frame number.
    p = f"(on/{max(1, frames - 1)})"
    amount = 0.14 * intensity   # zoom travel
    pan = 0.10 * intensity      # pan travel as a fraction of the frame

    if motion == "static":
        # Still sitting at a slight zoom keeps every scene visually consistent.
        z = "1.02"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "push_in":
        z = f"(1.0+{amount}*{p})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pull_out":
        z = f"(1.0+{amount}-{amount}*{p})"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion in ("pan_left", "pan_right"):
        z = f"{1.0 + pan:.4f}"
        travel = f"(iw-iw/zoom)"
        frac = p if motion == "pan_right" else f"(1-{p})"
        x = f"{travel}*{frac}"
        y = "ih/2-(ih/zoom/2)"
    elif motion in ("pan_up", "pan_down"):
        z = f"{1.0 + pan:.4f}"
        travel = f"(ih-ih/zoom)"
        frac = p if motion == "pan_down" else f"(1-{p})"
        x = "iw/2-(iw/zoom/2)"
        y = f"{travel}*{frac}"
    else:  # ken_burns - zoom in while drifting diagonally
        z = f"(1.0+{amount * 1.3:.4f}*{p})"
        x = f"(iw-iw/zoom)*(0.35+0.30*{p})"
        y = f"(ih-ih/zoom)*(0.30+0.25*{p})"

    return (
        f"zoompan=z='{z}':x='{x}':y='{y}'"
        f":d=1:s={width}x{height}:fps={fps}"
    )


def fit_chain(fit: str, width: int, height: int, blur_strength: int = 28) -> str:
    """Scale a source onto the supersampled canvas.

    cover    - fill the frame, crop the overflow (default; no letterboxing)
    blur_pad - fit the whole frame, fill the sides with a blurred blow-up
    contain  - fit the whole frame on a flat colour background
    """
    cw, ch = width * SUPERSAMPLE, height * SUPERSAMPLE
    if fit == "cover":
        return (
            f"scale={cw}:{ch}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={cw}:{ch},setsar=1"
        )
    if fit == "blur_pad":
        return (
            f"split=2[bg][fg];"
            f"[bg]scale={cw}:{ch}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={cw}:{ch},gblur=sigma={blur_strength},eq=brightness=-0.06:saturation=1.1[bgb];"
            f"[fg]scale={cw}:{ch}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
    if fit == "contain":
        return (
            f"scale={cw}:{ch}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        )
    raise ValueError(f"unknown fit {fit!r}; choose from cover, blur_pad, contain")
