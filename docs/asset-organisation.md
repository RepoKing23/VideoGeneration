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

## Censoring instead of cropping

When the client wants the full photo shown, privacy comes from a blur strip
over the eyes plus a black canvas, declared per photo in prep.json:

```json
{ "canvas": true, "censor": {"y0": 0.0, "y1": 0.30, "blur": 90} }
```

The declared rect is the guaranteed-censored core - the feathered edge is
drawn outside it, because feathering inward leaves a half-blended strip of
recognisable detail just inside the band. Sharpening must run before the
censor, never after, or it re-introduces exactly the edges the blur removed.

Verify with high-frequency energy: render a control without the censor and
require a >95% drop inside the band. Measure inset ~8px from the photo/canvas
boundary - JPEG ringing along that hard edge reads as fake detail.

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
which would paste a white rectangle over the footage. Run them through
`scripts/prepare_logo.py`, which writes the prepared versions into
`media/logo/`:

```bash
python3 scripts/prepare_logo.py "Brand logo.png" --name brand-logo
```

Deriving alpha as a plain `255 - luminance` looks right and is wrong: a
mid-grey anti-aliased stroke becomes a half-transparent pixel, so thin
lettering renders at under half strength and washes out over footage. The
first pass at this logo produced **zero** fully-opaque pixels, mean alpha 113.
The script instead maps anything clearly ink to fully opaque and fills the
mark with one solid colour, leaving only true edge pixels partial.

It writes:

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

Check what is *behind* it too, not just the average brightness. A logo sized
to fill the frame width may look bolder but overlap a subject's hair, and a
dark mark over dark hair is invisible whatever its size. Measure where the
subject starts:

```python
# fraction of dark pixels per row band - the subject's head shows up as a jump
(band < 110).mean()
```

and size the mark to fit the clean region above it.

`watermark.start` / `end` / `fade` limit it to the stretch where it reads.
