# Instagram Reels Studio

A repeatable pipeline for cutting vertical reels from your own clips and
images, with animated captions burned in. Drop media in a folder, write the
captions, render.

Output is 1080x1920, 30fps, H.264 + AAC with `+faststart` — Instagram's
preferred delivery spec, so nothing gets re-encoded harder than it has to be.

## Quick start

```bash
# 1. see what media you have
python3 scripts/inspect_media.py media

# 2. scaffold a project from that media plus a caption script
python3 scripts/new_project.py --name launch \
    --media media --captions projects/launch/captions.txt \
    --duration 25 --music media/audio/track.mp3 --handle "@yourhandle"

# 3. fast draft to check the edit
python3 src/build_reel.py projects/launch/project.json --preview

# 4. final render
python3 src/build_reel.py projects/launch/project.json
```

Check the pipeline is healthy at any time, with no media of your own:

```bash
./scripts/selftest.sh
```

## Getting your media in

Put clips and images under `media/`:

```
media/
  clips/    your video files (.mp4 .mov .m4v ...)
  images/   your stills (.jpg .png .heic ...)
  audio/    music beds and voiceovers
  fonts/    caption fonts (Anton, Bebas Neue, Poppins included)
  logo/     watermark art
```

Filenames sort alphabetically and that becomes the default scene order, so
prefixing `01_`, `02_` is the easiest way to lock a running order up front.

## How a reel is described

Everything about a reel lives in one `project.json`. Full field reference in
[docs/project-format.md](docs/project-format.md). The short version:

```jsonc
{
  "output": { "width": 1080, "height": 1920, "fps": 30, "file": "out/reel.mp4" },
  "style":  { "font": "Anton", "caption_preset": "word_pop", "accent": "#FFE600" },
  "grade":  { "contrast": 1.05, "saturation": 1.10, "vignette": true },
  "audio":  { "music": "media/audio/track.mp3", "music_gain_db": -9 },
  "scenes": [
    {
      "src": "media/clips/01_opener.mp4",
      "start": 2.0,          // in-point inside the source clip
      "duration": 3.2,       // how long it holds in the reel
      "fit": "cover",
      "motion": "push_in",
      "captions": [
        { "text": "Stop scrolling", "start": 0.1, "end": 2.0,
          "accent_words": ["stop"] }
      ]
    }
  ]
}
```

Caption times inside a scene are relative to that scene, so re-ordering or
re-timing scenes does not force you to re-time every caption.

## Caption animations

| preset | what it does |
| --- | --- |
| `word_pop` | one word at a time, large and centred, with a scale punch |
| `stack_reveal` | words accumulate on the line, newest word pops in accent colour |
| `karaoke_line` | full line up front, each word lights up on its beat |
| `slide_up` | line rises into place and fades |
| `typewriter` | characters revealed left to right |
| `bounce` | line drops in with an overshoot |

Set one as the default in `style.caption_preset` and override per caption with
`"preset"`. Captions are rendered through libass, which is what makes per-word
timing and scale tweens possible.

## Framing and camera moves

`fit` decides how a source fills a 9:16 frame:

- `cover` — fill and crop the overflow (default)
- `blur_pad` — fit the whole frame, fill the sides with a blurred blow-up
- `contain` — fit the whole frame on black

`motion` adds a camera move: `static`, `push_in`, `pull_out`, `pan_left`,
`pan_right`, `pan_up`, `pan_down`, `ken_burns`. Scale it with `intensity`
(1.0 default). Every move is cropped out of a 2x supersampled canvas, which
is what keeps it smooth rather than stepping a pixel at a time.

## Layout

```
src/reel/       the engine (config, captions, motion, render)
src/build_reel.py   CLI entry point
scripts/        media inspector, project scaffolder, self-test
projects/<name>/    project.json + captions.txt + rendered output
media/          your source material
work/           intermediates, safe to delete
```

Rendering runs in three passes — normalise each scene, chain them with
transitions, then grade/caption/mix — so a failure points at one stage
instead of one unreadable filtergraph.

## Requirements

ffmpeg built with `libass`, `libfreetype` and `libx264`, plus Python 3.11+.
On Debian/Ubuntu: `apt-get install ffmpeg`.
