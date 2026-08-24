# How assets are organised

One shared library, one folder per reel. Raw originals are never edited or
deleted, so any reel can be recut from scratch later.

```
media/
  raw/<shoot>/            originals exactly as uploaded (HEIC, MOV, ...)
  library/
    clips/<shoot>/        usable video, timestamp-named
    images/<shoot>/       usable stills, HEIC converted to JPEG
    audio/<shoot>/
  fonts/                  caption fonts
  catalog.json            every asset with dimensions, duration, capture time

projects/<date>-<slug>/
  project.json            the edit
  prep.json               per-photo crop / straighten / brighten recipe
  captions.txt            caption script
  voiceover-script.md     VO script, if there is one
  assets/                 prepped derivatives for this reel only
  out/                    rendered reel
```

`<shoot>` is `YYYY-MM-DD-subject`, e.g. `2026-08-23-lip-filler`.

## Adding a new batch

```bash
# 1. drop files anywhere under media/, then file them
python3 scripts/organize_media.py --shoot 2026-09-01-facial --dry-run
python3 scripts/organize_media.py --shoot 2026-09-01-facial

# 2. see what arrived
python3 scripts/inspect_media.py media/library
```

Assets are renamed to `YYYYMMDD-HHMMSS_<original>`, taken from EXIF or container
metadata. That makes before/after ordering fall out of a plain sort instead of
depending on someone remembering which file came first.

## Why derivatives live with the project

A crop that protects a client's privacy, or a colour match between a before and
an after, is a decision about *one reel*. Keeping those in
`projects/<name>/assets/` means a later reel that reuses the same source starts
from the untouched original rather than inheriting an edit made for a different
purpose.

## Privacy crops

Crops that remove a face are declared in `project.json` as a scene `crop`, not
baked into a file:

```json
{ "src": "...", "crop": {"x": 0.2917, "y": 0.0, "w": 0.7083, "h": 1.0} }
```

Cropping runs before framing and before any camera move, so a later pan or zoom
cannot bring the removed region back. The value is visible in review and in the
diff, which a pre-cropped file would not be.

Always verify with a dense sweep before delivering:

```bash
ffmpeg -i out/reel.mp4 -vf "fps=2,scale=150:-1,tile=9x4" -frames:v 1 sweep.jpg
```

## Logos

Brand marks usually arrive as dark art on a white background with no alpha,
which would paste a white rectangle over the footage. `media/logo/` holds
prepared versions instead:

- `*-dark.png` — original ink, transparent background, for bright frames
- `*-white.png` — same shape in white, for dark frames

Both are trimmed to the ink so the configured `width` is the visible width
rather than the width of a mostly-empty square.

Pick per shot rather than globally. Measure before deciding:

```python
# mean luminance of the band the logo will occupy
im.crop((int(w*0.2), int(h*0.84), int(w*0.8), int(h*0.94))).convert("L")
```

Above ~170 use the dark mark, below ~130 use the white one. In between, move
it — a mark straddling a light/dark edge loses half of itself.

`watermark.start` / `end` / `fade` limit it to the stretch where it reads.
