# House styles

Looks that shipped and should be reused as-is unless the client asks
otherwise. Reference project in parentheses.

## "Zen" — calm dark-luxe (projects/zen-clinic-room)

The client-approved style for calm/mood reels. Reuse both halves together.

### Intro title

Generate with `scripts/zen_intro.py` — do not restyle it, just change the
words and background:

```
python3 scripts/zen_intro.py <bg.png> <out.mp4> \
    --line1 "find your calm" --line2 "A MOMENT JUST FOR YOU" --duration 5.2
```

- Headline: Allura script (auto-shrinks to fit), letters resolve one by one
  from a blur with a warm halo, rising as they sharpen.
- Thin gold rule (`#D9A94E`, end dots) grows outward from the centre.
- Subline: Poppins Light, spaced caps, tracking eases wider as it fades in.
- Soft bokeh motes drift upward; at the end everything lifts and dissolves.
- Background: a 1080x1920 still from the footage (pre-crop a vertical slice
  from landscape sources), dimmed by the built-in veil (`--veil 0.30`).

### Captions and grade (project.json)

- `style`: font Poppins, preset `slide_up`, size ~88, lowercase,
  `letter_spacing` 3, primary `#FFFFFF`, accent gold `#D9A94E`,
  outline 2.5 in `#14100E`, shadow 1.5, position `center_low`.
- Transitions: long and soft only — `fadeblack` / `dissolve` / `fade`
  at 0.7–0.8s. No wipes, slides, or zooms.
- Motion: `static` where the source camera already moves; otherwise
  `push_in` / `pull_out` at intensity 0.3–0.35.
- Grade: contrast 1.02, brightness 0.03, gamma 1.08, saturation 0.98,
  warmth 0.015 — lifts dark footage without losing the moody feel.
- Music: `scripts/make_ambient.py` bed (beatless pads + singing-bowl
  chimes), `music_gain_db` -5.
- Logo: white LB mark top, two timed windows (intro + outro), fade 0.5.
