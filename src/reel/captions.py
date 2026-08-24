"""Animated caption generation.

Captions are emitted as an ASS subtitle file and burned in with libass, which
gives us per-word timing, scale/position tweens and colour transforms that
drawtext cannot do.  Each preset below is a different animation style; the
timing model is shared.

Time model
----------
A caption is a line of text with a start and end.  We split it into words and
distribute the span across them weighted by word length, so long words hold
the screen longer than short ones.  If the caller supplies explicit per-word
timings (e.g. from a transcript), those win.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .util import ass_time, hex_to_ass, hex_to_tag

PRESETS = (
    "word_pop",       # one word at a time, punchy scale pop  (Hormozi style)
    "stack_reveal",   # words accumulate on the line, newest word pops
    "karaoke_line",   # full line up front, words light up as spoken
    "slide_up",       # whole line slides up into place and fades
    "typewriter",     # characters revealed left to right
    "bounce",         # line drops in with an overshoot
)

# Vertical anchor presets, as a fraction of frame height.
POSITIONS = {
    "top": 0.18,
    "upper": 0.30,
    "center": 0.50,
    "center_low": 0.62,
    "lower": 0.74,
    "bottom": 0.86,
}


@dataclass
class Caption:
    text: str
    start: float
    end: float
    preset: str | None = None          # overrides the project default
    accent_words: list[str] = field(default_factory=list)
    position: str | None = None
    size: int | None = None            # overrides the project default
    colour: str | None = None          # overrides style.primary for this line
    outline_colour: str | None = None  # overrides style.outline_colour
    word_times: list[tuple[float, float]] | None = None

    @property
    def duration(self) -> float:
        return max(0.05, self.end - self.start)


@dataclass
class CaptionStyle:
    font: str = "Anton"
    size: int = 128
    primary: str = "#FFFFFF"
    accent: str = "#FFE600"
    outline_colour: str = "#000000"
    outline: float = 6.0
    shadow: float = 2.0
    position: str = "center_low"
    uppercase: bool = True
    max_chars_per_line: int = 16
    letter_spacing: float = 0.0
    box: bool = False                  # draw a filled plate behind the text
    box_colour: str = "#000000"
    box_alpha: int = 60                # 0 = opaque, 255 = invisible


def _split_words(text: str) -> list[str]:
    return [w for w in text.split() if w]


def _distribute(caption: Caption) -> list[tuple[str, float, float]]:
    """Return [(word, start, end)] in absolute seconds."""
    words = _split_words(caption.text)
    if not words:
        return []
    if caption.word_times and len(caption.word_times) == len(words):
        return [(w, s, e) for w, (s, e) in zip(words, caption.word_times)]

    # Weight by character count so "extraordinary" holds longer than "a".
    weights = [len(w) + 1.5 for w in words]
    total = sum(weights)
    span = caption.duration
    out: list[tuple[str, float, float]] = []
    cursor = caption.start
    for word, weight in zip(words, weights):
        share = span * (weight / total)
        out.append((word, cursor, cursor + share))
        cursor += share
    return out


def _wrap(text: str, max_chars: int) -> str:
    """Greedy wrap into ASS hard line breaks."""
    if max_chars <= 0:
        return text
    lines: list[str] = []
    current = ""
    for word in _split_words(text):
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return r"\N".join(lines)


def _escape(text: str) -> str:
    """Escape ASS control characters in user text."""
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _is_accent(word: str, accent_words: list[str]) -> bool:
    stripped = word.strip(".,!?;:\"'()[]").lower()
    return any(stripped == a.strip().lower() for a in accent_words)


# --------------------------------------------------------------------------
# Preset renderers.  Each returns a list of ASS Dialogue body strings paired
# with their (start, end) times.
# --------------------------------------------------------------------------

def _size_tag(cap) -> str:
    return rf"\fs{cap.size}" if cap.size else ""


def _style_tags(cap, style) -> str:
    """Size and outline-colour overrides for one caption.

    A single text colour rarely survives a whole reel - white type vanishes on a
    bright frame and dark type disappears on dark footage. Overriding per line
    beats compromising the palette across the whole edit.
    """
    tags = _size_tag(cap)
    if cap.outline_colour:
        tags += rf"\3c{hex_to_tag(cap.outline_colour)}"
    return tags


def _base_colour(cap, style) -> str:
    return cap.colour or style.primary


def _preset_word_pop(cap, style, w, h, y):
    """One word at a time, centred and large, with a scale punch."""
    events = []
    for word, start, end in _distribute(cap):
        colour = style.accent if _is_accent(word, cap.accent_words) else _base_colour(cap, style)
        tag = (
            rf"{{\an5\pos({w // 2},{y})" + _style_tags(cap, style) +
            rf"\1c{hex_to_tag(colour)}"
            r"\fscx62\fscy62"
            r"\t(0,90,\fscx108\fscy108)"
            r"\t(90,150,\fscx100\fscy100)"
            r"\fad(0,40)}"
        )
        events.append((start, end, tag + _escape(word.upper() if style.uppercase else word)))
    return events


def _preset_stack_reveal(cap, style, w, h, y):
    """Words accumulate on the line; the newest word pops in accent colour."""
    timed = _distribute(cap)
    words = [t[0] for t in timed]
    events = []
    for idx, (_, start, end) in enumerate(timed):
        parts = []
        for j, word in enumerate(words[: idx + 1]):
            shown = word.upper() if style.uppercase else word
            if j == idx:
                parts.append(
                    rf"{{\1c{hex_to_tag(style.accent)}\fscx70\fscy70"
                    r"\t(0,110,\fscx105\fscy105)\t(110,170,\fscx100\fscy100)}"
                    + _escape(shown)
                )
            else:
                parts.append(rf"{{\1c{hex_to_tag(_base_colour(cap, style))}\fscx100\fscy100}}" + _escape(shown))
        line = _wrap_tagged(" ".join(parts), style.max_chars_per_line)
        events.append((start, end, rf"{{\an5\pos({w // 2},{y}){_style_tags(cap, style)}}}" + line))
    return events


def _preset_karaoke_line(cap, style, w, h, y):
    """Whole line visible from the start; each word lights up on its beat."""
    timed = _distribute(cap)
    parts = []
    for word, start, end in timed:
        centis = max(1, int(round((end - start) * 100)))
        shown = word.upper() if style.uppercase else word
        parts.append(rf"{{\k{centis}}}" + _escape(shown))
    body = _wrap_tagged(" ".join(parts), style.max_chars_per_line)
    # Karaoke normally takes its two colours from the style: PrimaryColour is
    # the filled (sung) word, SecondaryColour the not-yet-filled text. A
    # per-caption override has to set both explicitly to reach this preset.
    colours = ""
    if cap.colour:
        colours = rf"\2c{hex_to_tag(cap.colour)}\1c{hex_to_tag(style.accent)}"
    tag = rf"{{\an5\pos({w // 2},{y}){_style_tags(cap, style)}{colours}\fad(120,120)}}"
    return [(cap.start, cap.end, tag + body)]


def _preset_slide_up(cap, style, w, h, y):
    """Line rises into place and fades, one event for the whole caption."""
    body = _wrap(_escape(cap.text.upper() if style.uppercase else cap.text), style.max_chars_per_line)
    tag = (
        rf"{{\an5\move({w // 2},{y + 70},{w // 2},{y},0,260)"
        + _style_tags(cap, style) +
        rf"\1c{hex_to_tag(_base_colour(cap, style))}\fad(180,180)}}"
    )
    return [(cap.start, cap.end, tag + body)]


def _preset_typewriter(cap, style, w, h, y):
    """Characters revealed left to right, then the full line holds."""
    text = cap.text.upper() if style.uppercase else cap.text
    chars = list(text)
    n = len(chars)
    if n == 0:
        return []
    # Spend 60% of the caption typing, hold the rest.
    type_span = cap.duration * 0.6
    step = type_span / n
    events = []
    for i in range(1, n + 1):
        start = cap.start + (i - 1) * step
        end = cap.start + i * step if i < n else cap.end
        partial = _wrap(_escape("".join(chars[:i])), style.max_chars_per_line)
        cursor = "|" if i < n else ""
        tag = rf"{{\an5\pos({w // 2},{y}){_style_tags(cap, style)}\1c{hex_to_tag(_base_colour(cap, style))}}}"
        events.append((start, end, tag + partial + cursor))
    return events


def _preset_bounce(cap, style, w, h, y):
    """Line drops in from above with an overshoot, then settles."""
    body = _wrap(_escape(cap.text.upper() if style.uppercase else cap.text), style.max_chars_per_line)
    tag = (
        rf"{{\an5\pos({w // 2},{y})" + _style_tags(cap, style) +
        rf"\1c{hex_to_tag(_base_colour(cap, style))}"
        r"\fscx40\fscy40\frz-4"
        r"\t(0,140,\fscx112\fscy112\frz2)"
        r"\t(140,230,\fscx96\fscy96\frz0)"
        r"\t(230,300,\fscx100\fscy100)"
        r"\fad(0,150)}"
    )
    return [(cap.start, cap.end, tag + body)]


def _wrap_tagged(tagged: str, max_chars: int) -> str:
    """Wrap a string that already contains ASS override blocks.

    Length is measured on visible text only, so override tags do not count
    toward the line budget.
    """
    if max_chars <= 0:
        return tagged
    import re

    tokens = tagged.split(" ")
    lines: list[str] = []
    current: list[str] = []
    visible_len = 0
    for token in tokens:
        plain = re.sub(r"\{[^}]*\}", "", token)
        add = len(plain) + (1 if current else 0)
        if visible_len + add > max_chars and current:
            lines.append(" ".join(current))
            current = [token]
            visible_len = len(plain)
        else:
            current.append(token)
            visible_len += add
    if current:
        lines.append(" ".join(current))
    return r"\N".join(lines)


_RENDERERS = {
    "word_pop": _preset_word_pop,
    "stack_reveal": _preset_stack_reveal,
    "karaoke_line": _preset_karaoke_line,
    "slide_up": _preset_slide_up,
    "typewriter": _preset_typewriter,
    "bounce": _preset_bounce,
}


_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{font},{size},{primary},{secondary},{outline_c},{back_c},0,0,0,0,100,100,{spacing},0,{border_style},{outline},{shadow},5,60,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(
    captions: list[Caption],
    style: CaptionStyle,
    width: int,
    height: int,
    default_preset: str = "word_pop",
) -> str:
    """Render a list of captions into a complete ASS subtitle document."""
    # For karaoke the style's PrimaryColour is the *filled* (sung) colour and
    # SecondaryColour is the pre-fill colour, so they swap versus other presets.
    uses_karaoke = any(
        (c.preset or default_preset) == "karaoke_line" for c in captions
    )
    if uses_karaoke:
        primary, secondary = style.accent, style.primary
    else:
        primary, secondary = style.primary, style.accent

    header = _HEADER.format(
        w=width,
        h=height,
        font=style.font,
        size=style.size,
        primary=hex_to_ass(primary),
        secondary=hex_to_ass(secondary),
        outline_c=hex_to_ass(style.outline_colour),
        back_c=hex_to_ass(style.box_colour, alpha=style.box_alpha),
        spacing=style.letter_spacing,
        border_style=3 if style.box else 1,
        outline=style.outline,
        shadow=style.shadow,
    )

    lines = [header]
    for cap in captions:
        preset = cap.preset or default_preset
        if preset not in _RENDERERS:
            raise ValueError(
                f"unknown caption preset {preset!r}; choose from {', '.join(PRESETS)}"
            )
        anchor = POSITIONS.get(cap.position or style.position)
        if anchor is None:
            raise ValueError(
                f"unknown caption position {cap.position or style.position!r}; "
                f"choose from {', '.join(POSITIONS)}"
            )
        y = int(height * anchor)
        for start, end, body in _RENDERERS[preset](cap, style, width, height, y):
            if end <= start:
                continue
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{body}"
            )
    return "\n".join(lines) + "\n"
