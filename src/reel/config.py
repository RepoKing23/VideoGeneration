"""Project configuration: load, validate, apply defaults."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .captions import PRESETS, POSITIONS, Caption, CaptionStyle
from .motion import MOTIONS

# Transitions accepted for scene changes.  "cut" is a hard cut (no blend).
TRANSITIONS = (
    "cut", "fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown", "circleopen",
    "circleclose", "radial", "smoothleft", "smoothright", "smoothup",
    "smoothdown", "pixelize", "fadeblack", "fadewhite", "zoomin",
)


@dataclass
class Scene:
    src: str
    duration: float = 3.0
    start: float = 0.0                 # in-point within the source clip
    fit: str = "cover"
    motion: str = "push_in"
    intensity: float = 1.0
    speed: float = 1.0
    source_audio: bool = False
    source_audio_gain_db: float = -3.0
    transition: str = "fade"           # transition *into* this scene
    transition_duration: float = 0.35
    captions: list[Caption] = field(default_factory=list)


@dataclass
class Project:
    name: str = "reel"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    out_file: str = "out/reel.mp4"
    crf: int = 19
    x264_preset: str = "medium"
    style: CaptionStyle = field(default_factory=CaptionStyle)
    caption_preset: str = "word_pop"
    scenes: list[Scene] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)   # absolute-timed
    grade: dict = field(default_factory=dict)
    audio: dict = field(default_factory=dict)
    watermark: dict = field(default_factory=dict)
    root: Path = Path(".")          # folder holding project.json
    repo_root: Path = Path(".")     # repo root, where media/ lives

    def resolve(self, rel: str) -> Path:
        """Resolve a path relative to the project folder, then the repo root.

        Media usually lives in the shared media/ folder at the repo root, but a
        project may keep its own assets alongside project.json.  Paths that do
        not exist yet (outputs) resolve against the project folder.
        """
        p = Path(rel)
        if p.is_absolute():
            return p
        local = self.root / p
        if local.exists():
            return local
        shared = self.repo_root / p
        if shared.exists():
            return shared
        return local


def _caption(raw: dict) -> Caption:
    missing = {"text", "start", "end"} - raw.keys()
    if missing:
        raise ValueError(f"caption is missing {sorted(missing)}: {raw}")
    preset = raw.get("preset")
    if preset and preset not in PRESETS:
        raise ValueError(f"unknown caption preset {preset!r}; choose from {', '.join(PRESETS)}")
    position = raw.get("position")
    if position and position not in POSITIONS:
        raise ValueError(f"unknown position {position!r}; choose from {', '.join(POSITIONS)}")
    return Caption(
        text=str(raw["text"]),
        start=float(raw["start"]),
        end=float(raw["end"]),
        preset=preset,
        accent_words=list(raw.get("accent_words", [])),
        position=position,
        word_times=[tuple(t) for t in raw["word_times"]] if raw.get("word_times") else None,
    )


def load(path: str | Path) -> Project:
    path = Path(path).resolve()
    raw = json.loads(path.read_text())
    root = path.parent

    out = raw.get("output", {})
    style_raw = dict(raw.get("style", {}))
    caption_preset = style_raw.pop("caption_preset", "word_pop")
    if caption_preset not in PRESETS:
        raise ValueError(
            f"unknown caption_preset {caption_preset!r}; choose from {', '.join(PRESETS)}"
        )
    known = CaptionStyle().__dict__.keys()
    unknown = set(style_raw) - set(known)
    if unknown:
        raise ValueError(f"unknown style keys {sorted(unknown)}; valid: {sorted(known)}")
    style = CaptionStyle(**style_raw)
    if style.position not in POSITIONS:
        raise ValueError(f"unknown style position {style.position!r}")

    scenes: list[Scene] = []
    for i, s in enumerate(raw.get("scenes", [])):
        if "src" not in s:
            raise ValueError(f"scene {i} has no 'src'")
        trans = s.get("transition", {})
        if isinstance(trans, str):
            trans = {"type": trans}
        ttype = trans.get("type", "fade" if i else "cut")
        if ttype not in TRANSITIONS:
            raise ValueError(
                f"scene {i}: unknown transition {ttype!r}; choose from {', '.join(TRANSITIONS)}"
            )
        motion = s.get("motion", "push_in")
        if motion not in MOTIONS:
            raise ValueError(
                f"scene {i}: unknown motion {motion!r}; choose from {', '.join(MOTIONS)}"
            )
        fit = s.get("fit", "cover")
        if fit not in ("cover", "blur_pad", "contain"):
            raise ValueError(f"scene {i}: unknown fit {fit!r}")
        scenes.append(Scene(
            src=s["src"],
            duration=float(s.get("duration", 3.0)),
            start=float(s.get("start", 0.0)),
            fit=fit,
            motion=motion,
            intensity=float(s.get("intensity", 1.0)),
            speed=float(s.get("speed", 1.0)),
            source_audio=bool(s.get("source_audio", False)),
            source_audio_gain_db=float(s.get("source_audio_gain_db", -3.0)),
            transition="cut" if i == 0 else ttype,
            transition_duration=0.0 if i == 0 else float(trans.get("duration", 0.35)),
            captions=[_caption(c) for c in s.get("captions", [])],
        ))

    if not scenes:
        raise ValueError("project has no scenes")

    return Project(
        name=raw.get("name", path.parent.name),
        width=int(out.get("width", 1080)),
        height=int(out.get("height", 1920)),
        fps=int(out.get("fps", 30)),
        out_file=out.get("file", f"out/{raw.get('name', 'reel')}.mp4"),
        crf=int(out.get("crf", 19)),
        x264_preset=out.get("preset", "medium"),
        style=style,
        caption_preset=caption_preset,
        scenes=scenes,
        captions=[_caption(c) for c in raw.get("captions", [])],
        grade=raw.get("grade", {}),
        audio=raw.get("audio", {}),
        watermark=raw.get("watermark", {}),
        root=root,
        repo_root=Path(__file__).resolve().parents[2],
    )


def timeline(project: Project) -> tuple[list[float], float]:
    """Return (scene start offsets, total duration) accounting for overlaps."""
    starts: list[float] = []
    cursor = 0.0
    for i, scene in enumerate(project.scenes):
        if i == 0:
            starts.append(0.0)
            cursor = scene.duration
        else:
            overlap = min(
                scene.transition_duration,
                scene.duration * 0.9,
                project.scenes[i - 1].duration * 0.9,
            )
            start = cursor - overlap
            starts.append(start)
            cursor = start + scene.duration
    return starts, cursor
