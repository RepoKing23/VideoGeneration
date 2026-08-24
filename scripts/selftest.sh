#!/usr/bin/env bash
# End-to-end check of the render pipeline using generated test media.
# Renders a short reel exercising every fit, motion, transition and caption
# preset, then drops a contact sheet next to it.  No user media required.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
T=work/_selftest_media
P=work/_selftest_project
mkdir -p "$T" "$P"

echo "generating test media..."
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc2=size=1920x1080:rate=30:duration=8" \
  -f lavfi -i "sine=frequency=420:duration=8" \
  -c:v libx264 -crf 20 -pix_fmt yuv420p -c:a aac -shortest "$T/land_a.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "smptebars=size=1920x1080:rate=30:duration=6" \
  -c:v libx264 -crf 20 -pix_fmt yuv420p -an "$T/land_b.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=1080x1920:rate=30:duration=6" \
  -c:v libx264 -crf 20 -pix_fmt yuv420p -an "$T/vert_c.mp4"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "gradients=size=2400x1600:duration=1:rate=1" \
  -frames:v 1 "$T/img_a.jpg"
ffmpeg -hide_banner -loglevel error -y -f lavfi -i "anoisesrc=d=30:c=pink:a=0.1" \
  -af "highpass=200,lowpass=3000" -c:a libmp3lame -b:a 192k "$T/music.mp3"

cat > "$P/project.json" <<'JSON'
{
  "name": "_selftest",
  "output": {"width": 1080, "height": 1920, "fps": 30, "file": "selftest.mp4", "crf": 22, "preset": "veryfast"},
  "style": {"font": "Anton", "caption_preset": "word_pop", "size": 150, "primary": "#FFFFFF",
            "accent": "#FFE600", "outline": 7, "position": "center_low", "max_chars_per_line": 16},
  "grade": {"contrast": 1.06, "saturation": 1.12, "warmth": 0.4, "vignette": true,
            "fade_in": 0.3, "fade_out": 0.5},
  "audio": {"music": "work/_selftest_media/music.mp3", "music_gain_db": -12, "fade_in": 0.4, "fade_out": 1.0},
  "watermark": {"text": "@selftest", "position": "bottom", "opacity": 0.5, "size": 36},
  "scenes": [
    {"src": "work/_selftest_media/land_a.mp4", "start": 1.0, "duration": 2.6, "fit": "cover", "motion": "push_in",
     "source_audio": true, "source_audio_gain_db": -18,
     "captions": [{"text": "Stop scrolling right now", "start": 0.1, "end": 2.4, "accent_words": ["stop", "now"]}]},
    {"src": "work/_selftest_media/img_a.jpg", "duration": 2.4, "fit": "cover", "motion": "ken_burns",
     "transition": {"type": "fade", "duration": 0.35},
     "captions": [{"text": "This changes everything", "start": 0.2, "end": 2.2, "preset": "stack_reveal"}]},
    {"src": "work/_selftest_media/land_b.mp4", "duration": 2.4, "fit": "blur_pad", "motion": "pan_right",
     "transition": {"type": "slideleft", "duration": 0.4},
     "captions": [{"text": "Watch what happens next", "start": 0.2, "end": 2.2, "preset": "bounce", "position": "upper"}]},
    {"src": "work/_selftest_media/vert_c.mp4", "duration": 2.6, "fit": "cover", "motion": "pull_out",
     "transition": {"type": "wipeup", "duration": 0.3},
     "captions": [{"text": "Save this for later", "start": 0.2, "end": 2.4, "preset": "karaoke_line"}]}
  ]
}
JSON

echo "rendering..."
python3 src/build_reel.py "$P/project.json"

OUT="$P/selftest.mp4"
ffmpeg -hide_banner -loglevel error -y -i "$OUT" \
  -vf "select='not(mod(n\,34))',scale=270:-1,tile=4x2" -frames:v 1 "$P/contact_sheet.png"
echo
echo "PASS - reel:          $OUT"
echo "       contact sheet: $P/contact_sheet.png"
