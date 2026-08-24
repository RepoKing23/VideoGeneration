# project.json reference

Every value below is optional unless marked **required**. Paths resolve
against the project folder first, then the repo root — so both
`media/clips/a.mp4` and a file sitting next to `project.json` work.

## `output`

| key | default | notes |
| --- | --- | --- |
| `width` / `height` | `1080` / `1920` | Instagram's native reel frame |
| `fps` | `30` | 30 is the safe delivery rate; 60 doubles file size for little gain |
| `file` | `out/<name>.mp4` | relative to the project folder |
| `crf` | `19` | lower is better quality and bigger; 17–23 is the useful range |
| `preset` | `medium` | x264 speed/efficiency trade-off |

## `style`

Defaults for every caption. Individual captions can override `preset` and
`position`.

| key | default | notes |
| --- | --- | --- |
| `font` | `Anton` | family name; the file must be in `media/fonts/` |
| `caption_preset` | `word_pop` | see the preset table below |
| `size` | `128` | in a 1920-tall frame, ~7% of frame height |
| `primary` | `#FFFFFF` | main text colour |
| `accent` | `#FFE600` | highlight colour for accented words and karaoke fill |
| `outline_colour` | `#000000` | |
| `outline` | `6.0` | thickness; keep it high, captions get watched over busy footage |
| `shadow` | `2.0` | |
| `position` | `center_low` | `top`, `upper`, `center`, `center_low`, `lower`, `bottom` |
| `uppercase` | `true` | |
| `max_chars_per_line` | `16` | wrap width, measured in visible characters |
| `letter_spacing` | `0.0` | |
| `box` | `false` | draw a filled plate behind the text instead of an outline |
| `box_colour` | `#000000` | |
| `box_alpha` | `60` | 0 opaque, 255 invisible |

Keep captions clear of Instagram's UI: the bottom ~15% of the frame sits under
the caption/audio strip and the top ~10% under the header. `center_low` is the
safest home for the main line.

## `scenes` (**required**, at least one)

| key | default | notes |
| --- | --- | --- |
| `src` | **required** | video or image path |
| `duration` | `3.0` | how long the scene holds in the finished reel |
| `start` | `0.0` | in-point inside the source clip (ignored for images) |
| `fit` | `cover` | `cover`, `blur_pad`, `contain` |
| `motion` | `push_in` | `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `ken_burns` |
| `intensity` | `1.0` | scales the camera move; `0.5` is subtle, `2.0` is aggressive |
| `speed` | `1.0` | `2.0` is double speed; the engine pulls a longer source slice to fill the scene |
| `source_audio` | `false` | keep the clip's own sound |
| `source_audio_gain_db` | `-3.0` | |
| `transition` | `fade` @ `0.35s` | transition *into* this scene; ignored on the first |
| `captions` | `[]` | times are relative to this scene |

Transitions: `cut`, `fade`, `dissolve`, `wipeleft`, `wiperight`, `wipeup`,
`wipedown`, `slideleft`, `slideright`, `slideup`, `slidedown`, `circleopen`,
`circleclose`, `radial`, `smoothleft`, `smoothright`, `smoothup`,
`smoothdown`, `pixelize`, `fadeblack`, `fadewhite`, `zoomin`.

A transition overlaps the two scenes, so it shortens the total runtime. The
engine clamps the overlap to 90% of the shorter neighbour, so a long
transition on a short scene degrades instead of breaking.

## `captions`

Either inside a scene (times relative to the scene) or at the top level
(times absolute on the finished timeline).

| key | default | notes |
| --- | --- | --- |
| `text` | **required** | |
| `start` / `end` | **required** | seconds |
| `preset` | `style.caption_preset` | override for this line |
| `position` | `style.position` | override for this line |
| `accent_words` | `[]` | words drawn in the accent colour, matched case-insensitively |
| `word_times` | auto | `[[start, end], ...]`, one pair per word, for transcript-accurate timing |

Without `word_times`, the line's span is split across its words weighted by
word length, so long words hold longer than short ones. That reads naturally
for scripted captions; supply `word_times` when syncing to real speech.

### Presets

| preset | behaviour | good for |
| --- | --- | --- |
| `word_pop` | one word at a time, big, scale punch | hooks, punchy voiceover |
| `stack_reveal` | words accumulate, newest pops in accent | lists, building a point |
| `karaoke_line` | line up front, words light up on beat | lyrics, talking head |
| `slide_up` | line rises and fades | calm, editorial |
| `typewriter` | characters revealed left to right | reveals, suspense |
| `bounce` | line drops in with overshoot | energetic, playful |

## `grade`

| key | default | notes |
| --- | --- | --- |
| `contrast` | `1.0` | |
| `brightness` | `0.0` | |
| `saturation` | `1.0` | `1.10`–`1.15` gives phone-screen pop |
| `gamma` | `1.0` | |
| `warmth` | `0` | positive lifts red and drops blue |
| `vignette` | `false` | |
| `fade_in` / `fade_out` | `0.25` / `0.4` | fade from and to black, in seconds |

## `audio`

| key | default | notes |
| --- | --- | --- |
| `music` | none | loops automatically if shorter than the reel |
| `music_start` | `0` | in-point in the track — use it to start on the drop |
| `music_gain_db` | `-8` | |
| `fade_in` / `fade_out` | `0.4` / `1.2` | |
| `voiceover` | none | |
| `voiceover_start` | `0` | |
| `voiceover_gain_db` | `0` | |

When both music and a voiceover are present the music is ducked under the
voice with a sidechain compressor rather than just turned down, so it breathes
back up between phrases. The mix bus is limited at -0.4 dBFS so a hot music
bed will not clip on phone speakers.

## `watermark`

| key | default | notes |
| --- | --- | --- |
| `text` | none | e.g. `@yourhandle` |
| `position` | `bottom` | `top` or `bottom` |
| `opacity` | `0.55` | |
| `size` | `38` | |
| `font` | `style.font` | |
