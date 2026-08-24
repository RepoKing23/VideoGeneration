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

Commit your media to the working branch and push:

```bash
git checkout claude/instagram-reels-creation-l9i0z0
cp ~/your-footage/*.mp4 media/clips/
cp ~/your-photos/*.jpg media/images/
git add media/ && git commit -m "Add reel source media" && git push
```

GitHub rejects single files over 100MB, so trim or compress anything larger
before committing:

```bash
ffmpeg -i big.mov -c:v libx264 -crf 23 -vf scale=-2:1920 -c:a aac media/clips/big.mp4
```

Layout under `media/`:

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

## Picking a caption look

```bash
python3 scripts/style_sampler.py --font Anton --accent "#FFE600"
```

Renders a reel demoing all six presets over gradient backgrounds, so you are
judging the type rather than the footage. Swap `--font` and `--accent` to
preview a different treatment.

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

`word_pop` is the default and the safest high-retention choice.

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

## Audio

If you plan to add a trending track in the Instagram app, render silent — the
in-app track usually travels further than a baked-in one. The engine still
writes a silent AAC stream, because a few upload paths mishandle a file with
no audio stream at all. Set `"audio": {"silent_track": false}` to omit it.

Supply `audio.music` and it loops to length, fades at both ends, and passes
through a limiter. Add `audio.voiceover` too and the music ducks under the
voice with a sidechain compressor rather than just sitting quieter.

## Handwriting intro title

The CapCut-style opener: large script text written on letter by letter with a
soft glow, a small sun doodle, diamond sparkles, and the letters drifting apart
as the scene ends. Composited in PIL over a slow push-in, one frame at a time,
so every element's timing is explicit.

```bash
python3 scripts/title_intro.py bg.jpg out.mp4 \
    --line1 "another day" --line2 "at work" --doodle-label "cleo r"
```

Use the output as an ordinary scene (`motion: static` - the push-in is baked
in). White script needs a soft dark under-shadow to survive a bright
background; the script draws one automatically.

## Before / after split reveal

The comparison people actually stop for: a vertical divider sweeps across, one
side before, the other after, settling on a centre split.

```bash
python3 scripts/split_reveal.py before.jpg after.jpg out.mp4 --duration 4.2
```

It only works if the two stills are aligned and colour-matched. If the mouth
line jumps across the divider, or one side is brighter, it reads as a mistake
rather than a result. `scripts/prep_photos.py` handles both - measure the
offset by cross-correlating a region the treatment does not change (the nose,
not the lips) and split the correction between the two crops.

## Music

No licensed track to hand:

```bash
python3 scripts/make_lofi.py bed.wav --duration 18 --bpm 72
```

Synthesises a lo-fi bed - seventh-chord keys, lazy two-and-four beat, upright
bass, vinyl noise, rolled off hard at the top. Written rather than licensed, so
there is no rights question about using it commercially.

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
