"""The render pipeline.

Three passes, because one monolithic filtergraph is impossible to debug:

  1. normalise  - each scene becomes a 1080x1920 clip at the target fps with
                  its framing and camera move already baked in
  2. assemble   - scenes are chained with xfade/concat into one silent edit
  3. finish     - grade, burn captions, watermark, mix audio, encode

Intermediates land in work/<project>/ so a re-render only redoes what changed.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .captions import Caption, build_ass
from .config import Project, Scene, timeline
from .motion import fit_chain, zoompan_chain
from .util import escape_filter_path, ffmpeg, probe

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tif", ".tiff"}


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXT


def normalise_scene(project: Project, scene: Scene, index: int, workdir: Path) -> Path:
    """Pass 1: render one scene to a clean, uniform intermediate clip."""
    src = project.resolve(scene.src)
    if not src.exists():
        raise FileNotFoundError(f"scene {index}: missing source {src}")

    dst = workdir / f"scene_{index:03d}.mp4"
    frames = max(1, round(scene.duration * project.fps))
    chain = []
    if scene.crop:
        c = scene.crop
        # Cropping happens before framing, so a privacy crop is guaranteed to
        # remove the region rather than have a later pan bring it back.
        chain.append(
            f"crop=iw*{float(c['w'])}:ih*{float(c['h'])}"
            f":iw*{float(c['x'])}:ih*{float(c['y'])}"
        )
    chain += [
        fit_chain(scene.fit, project.width, project.height),
        zoompan_chain(scene.motion, project.width, project.height,
                      frames, project.fps, scene.intensity),
        "format=yuv420p",
    ]

    args: list[str] = []
    if _is_image(src):
        args += ["-loop", "1", "-framerate", str(project.fps), "-t", f"{scene.duration}", "-i", str(src)]
    else:
        # Source is trimmed before scaling so we never decode more than needed.
        # speed != 1 means we must pull a longer slice of source to fill the scene.
        source_span = scene.duration * scene.speed
        args += ["-ss", f"{scene.start}", "-t", f"{source_span}", "-i", str(src)]
        if scene.speed != 1.0:
            chain.insert(0, f"setpts=PTS/{scene.speed}")

    ffmpeg([
        *args,
        "-an",
        "-vf", ",".join(chain),
        "-t", f"{scene.duration}",
        "-r", str(project.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
        "-pix_fmt", "yuv420p",
        str(dst),
    ])
    return dst


def extract_scene_audio(project: Project, scene: Scene, index: int, workdir: Path) -> Path | None:
    """Pull a scene's own audio out to its own file, if it has any and wants it."""
    if not scene.source_audio:
        return None
    src = project.resolve(scene.src)
    if _is_image(src) or not probe(src)["has_audio"]:
        return None
    dst = workdir / f"scene_{index:03d}.m4a"
    span = scene.duration * scene.speed
    chain = []
    if scene.speed != 1.0:
        # atempo only accepts 0.5-2.0 per instance, so chain them.
        remaining, factor = scene.speed, []
        while remaining > 2.0:
            factor.append(2.0)
            remaining /= 2.0
        while remaining < 0.5:
            factor.append(0.5)
            remaining /= 0.5
        factor.append(remaining)
        chain += [f"atempo={f:.6f}" for f in factor]
    chain.append(f"volume={scene.source_audio_gain_db}dB")
    ffmpeg([
        "-ss", f"{scene.start}", "-t", f"{span}", "-i", str(src),
        "-vn", "-af", ",".join(chain),
        "-t", f"{scene.duration}",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        str(dst),
    ])
    return dst


def assemble(project: Project, clips: list[Path], workdir: Path) -> Path:
    """Pass 2: chain the scenes together with their transitions."""
    dst = workdir / "edit.mp4"
    if len(clips) == 1:
        shutil.copyfile(clips[0], dst)
        return dst

    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]

    steps: list[str] = []
    label = "0:v"
    running = project.scenes[0].duration
    for i in range(1, len(clips)):
        scene = project.scenes[i]
        nxt = f"v{i}"
        if scene.transition == "cut" or scene.transition_duration <= 0:
            steps.append(f"[{label}][{i}:v]concat=n=2:v=1:a=0[{nxt}]")
            running += scene.duration
        else:
            overlap = min(
                scene.transition_duration,
                scene.duration * 0.9,
                project.scenes[i - 1].duration * 0.9,
            )
            offset = running - overlap
            steps.append(
                f"[{label}][{i}:v]xfade=transition={scene.transition}"
                f":duration={overlap:.4f}:offset={offset:.4f}[{nxt}]"
            )
            running = offset + scene.duration
        label = nxt

    ffmpeg([
        *inputs,
        "-filter_complex", ";".join(steps),
        "-map", f"[{label}]",
        "-r", str(project.fps),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
        "-pix_fmt", "yuv420p",
        str(dst),
    ])
    return dst


def build_audio(project: Project, scene_audio: dict[int, Path],
                starts: list[float], total: float) -> tuple[list[str], list[str], str | None]:
    """Build the audio graph.  Returns (extra ffmpeg inputs, filter steps, label).

    Music sits under everything, scene audio drops in at its timeline offset,
    and a voiceover (if present) ducks the music via a sidechain compressor.
    """
    cfg = project.audio or {}
    inputs: list[str] = []
    steps: list[str] = []
    stems: list[str] = []
    idx = 1  # input 0 is the silent video edit

    music_label = None
    if cfg.get("music"):
        music = project.resolve(cfg["music"])
        if not music.exists():
            raise FileNotFoundError(f"music track not found: {music}")
        inputs += ["-stream_loop", "-1", "-ss", f"{cfg.get('music_start', 0)}", "-i", str(music)]
        gain = cfg.get("music_gain_db", -8)
        fade_in = cfg.get("fade_in", 0.4)
        fade_out = cfg.get("fade_out", 1.2)
        steps.append(
            f"[{idx}:a]atrim=0:{total:.4f},asetpts=PTS-STARTPTS,"
            f"volume={gain}dB,"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={max(0.0, total - fade_out):.4f}:d={fade_out},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[music]"
        )
        music_label = "music"
        idx += 1

    voice_label = None
    if cfg.get("voiceover"):
        voice = project.resolve(cfg["voiceover"])
        if not voice.exists():
            raise FileNotFoundError(f"voiceover not found: {voice}")
        inputs += ["-i", str(voice)]
        steps.append(
            f"[{idx}:a]volume={cfg.get('voiceover_gain_db', 0)}dB,"
            f"adelay={int(cfg.get('voiceover_start', 0) * 1000)}|{int(cfg.get('voiceover_start', 0) * 1000)},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[voice]"
        )
        voice_label = "voice"
        idx += 1

    # Duck the music under the voiceover instead of just turning it down.
    if music_label and voice_label:
        steps.append(f"[{voice_label}]asplit=2[voice_mix][voice_key]")
        steps.append(
            f"[{music_label}][voice_key]sidechaincompress="
            f"threshold=0.05:ratio=8:attack=20:release=400:makeup=1[ducked]"
        )
        stems += ["ducked", "voice_mix"]
    else:
        stems += [s for s in (music_label, voice_label) if s]

    for scene_index, path in sorted(scene_audio.items()):
        inputs += ["-i", str(path)]
        delay = int(round(starts[scene_index] * 1000))
        label = f"sa{scene_index}"
        steps.append(
            f"[{idx}:a]adelay={delay}|{delay},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[{label}]"
        )
        stems.append(label)
        idx += 1

    if not stems:
        # No audio sources.  Instagram accepts a video with no audio stream, but
        # a few upload paths behave better when one exists, so emit silence
        # unless the project explicitly opts out.
        if cfg.get("silent_track", True):
            inputs += ["-f", "lavfi", "-t", f"{total:.4f}",
                       "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
            steps.append(f"[{idx}:a]atrim=0:{total:.4f},asetpts=PTS-STARTPTS[aout]")
            return inputs, steps, "aout"
        return [], [], None

    if len(stems) == 1:
        mixed = stems[0]
    else:
        joined = "".join(f"[{s}]" for s in stems)
        steps.append(f"{joined}amix=inputs={len(stems)}:normalize=0:dropout_transition=0[mixed]")
        mixed = "mixed"

    # A limiter on the bus keeps a hot music bed from clipping on phone speakers.
    steps.append(
        f"[{mixed}]alimiter=limit=0.95:level=disabled,"
        f"atrim=0:{total:.4f},asetpts=PTS-STARTPTS[aout]"
    )
    return inputs, steps, "aout"


def video_finish_chain(project: Project, ass_path: Path | None, total: float) -> list[str]:
    """Grade, captions, watermark and top/tail fades for the final pass."""
    grade = project.grade or {}
    chain: list[str] = []

    eq_parts = []
    if grade.get("contrast", 1.0) != 1.0:
        eq_parts.append(f"contrast={grade['contrast']}")
    if grade.get("brightness", 0.0) != 0.0:
        eq_parts.append(f"brightness={grade['brightness']}")
    if grade.get("saturation", 1.0) != 1.0:
        eq_parts.append(f"saturation={grade['saturation']}")
    if grade.get("gamma", 1.0) != 1.0:
        eq_parts.append(f"gamma={grade['gamma']}")
    if eq_parts:
        chain.append("eq=" + ":".join(eq_parts))
    if grade.get("warmth"):
        # Positive warmth lifts red and drops blue slightly.
        w = float(grade["warmth"])
        chain.append(
            f"colorchannelmixer=rr={1 + 0.08 * w}:gg=1:bb={1 - 0.08 * w}"
        )
    if grade.get("vignette"):
        chain.append("vignette=angle=PI/5")

    if ass_path is not None:
        fonts_dir = project.repo_root / "media" / "fonts"
        if not fonts_dir.exists():
            fonts_dir = Path("media/fonts")
        chain.append(
            f"subtitles='{escape_filter_path(ass_path)}'"
            f":fontsdir='{escape_filter_path(fonts_dir)}'"
        )

    wm = project.watermark or {}
    if wm.get("text"):
        font_file = _font_file(project, wm.get("font", project.style.font))
        y = {"top": "h*0.06", "bottom": "h*0.90"}.get(wm.get("position", "bottom"), "h*0.90")
        chain.append(
            f"drawtext=fontfile='{escape_filter_path(font_file)}'"
            f":text='{wm['text']}'"
            f":fontcolor=white@{wm.get('opacity', 0.55)}"
            f":fontsize={wm.get('size', 38)}"
            f":x=(w-text_w)/2:y={y}"
            f":shadowcolor=black@0.5:shadowx=2:shadowy=2"
        )

    fade_in = (project.grade or {}).get("fade_in", 0.25)
    fade_out = (project.grade or {}).get("fade_out", 0.4)
    if fade_in:
        chain.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        chain.append(f"fade=t=out:st={max(0.0, total - fade_out):.4f}:d={fade_out}")

    chain.append("format=yuv420p")
    return chain


def _font_file(project: Project, family: str) -> Path:
    """Map a font family name to a file in media/fonts."""
    fonts_dir = project.repo_root / "media" / "fonts"
    if not fonts_dir.exists():
        fonts_dir = Path("media/fonts")
    wanted = family.lower().replace(" ", "")
    for path in sorted(fonts_dir.glob("*.[to]tf")):
        if path.stem.lower().replace(" ", "").replace("-", "").startswith(wanted):
            return path
    fallback = sorted(fonts_dir.glob("*.[to]tf"))
    if fallback:
        return fallback[0]
    return Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def collect_captions(project: Project, starts: list[float]):
    """Merge per-scene (relative) and top-level (absolute) captions."""
    out = list(project.captions)
    for i, scene in enumerate(project.scenes):
        for cap in scene.captions:
            shifted = Caption(
                text=cap.text,
                start=starts[i] + cap.start,
                end=starts[i] + cap.end,
                preset=cap.preset,
                accent_words=cap.accent_words,
                position=cap.position,
                word_times=(
                    [(starts[i] + s, starts[i] + e) for s, e in cap.word_times]
                    if cap.word_times else None
                ),
            )
            out.append(shifted)
    return sorted(out, key=lambda c: c.start)


def render(project: Project, workdir: Path | None = None, log=print) -> Path:
    """Run the full pipeline and return the path to the finished reel."""
    workdir = workdir or (project.repo_root / "work" / project.name)
    workdir.mkdir(parents=True, exist_ok=True)
    out_path = project.resolve(project.out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    starts, total = timeline(project)
    log(f"[1/3] normalising {len(project.scenes)} scenes -> "
        f"{project.width}x{project.height}@{project.fps} ({total:.2f}s total)")

    clips: list[Path] = []
    scene_audio: dict[int, Path] = {}
    for i, scene in enumerate(project.scenes):
        log(f"      scene {i}: {Path(scene.src).name} "
            f"[{scene.fit}/{scene.motion}] {scene.duration:.2f}s")
        clips.append(normalise_scene(project, scene, i, workdir))
        track = extract_scene_audio(project, scene, i, workdir)
        if track:
            scene_audio[i] = track

    log("[2/3] assembling transitions")
    edit = assemble(project, clips, workdir)

    captions = collect_captions(project, starts)
    ass_path = None
    if captions:
        ass_path = workdir / "captions.ass"
        ass_path.write_text(build_ass(
            captions, project.style, project.width, project.height, project.caption_preset
        ))
        log(f"      {len(captions)} captions -> {ass_path.name} "
            f"(preset: {project.caption_preset})")

    log("[3/3] grading, burning captions, mixing audio")
    audio_inputs, audio_steps, audio_label = build_audio(project, scene_audio, starts, total)
    vchain = video_finish_chain(project, ass_path, total)

    filter_steps = [f"[0:v]{','.join(vchain)}[vout]"] + audio_steps
    args = ["-i", str(edit), *audio_inputs,
            "-filter_complex", ";".join(filter_steps),
            "-map", "[vout]"]
    if audio_label:
        args += ["-map", f"[{audio_label}]", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
    else:
        args += ["-an"]
    args += [
        "-c:v", "libx264", "-preset", project.x264_preset, "-crf", str(project.crf),
        "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p",
        "-r", str(project.fps),
        "-movflags", "+faststart",
        "-t", f"{total:.4f}",
        str(out_path),
    ]
    ffmpeg(args)

    info = probe(out_path)
    size_mb = out_path.stat().st_size / 1e6
    log(f"done: {out_path}  {info['width']}x{info['height']} "
        f"{info['duration']:.2f}s {info['fps']}fps {size_mb:.1f}MB")
    return out_path
