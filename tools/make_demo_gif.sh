#!/usr/bin/env bash
# Turn a screen recording into a README GIF.
#
#   tools/make_demo_gif.sh demo/mp4/question1.mp4 docs/assets/demo-answer.gif 1400
#
# The recording is a one-off human take — that is why the trace of the run in it
# is committed alongside (red-team F-19). This step is the half that *is*
# repeatable: same source, same parameters, same output. The sources live in
# `demo/mp4/`, committed for exactly that reason, and the exact commands used
# for the shipped GIFs are recorded in docs/assets/CAPTURE.md.
#
# The third argument is the pixel row to crop the bottom at, in SOURCE
# coordinates: a screen recording carries a lot of empty page below the content,
# and cropping it is what keeps text legible after the GIF's 256-colour
# quantisation. `_TOP` drops Streamlit's toolbar. Nothing is cut, retimed or
# reordered — the whole take is preserved, only cropped and scaled.
set -euo pipefail

usage() {
  echo "usage: make_demo_gif.sh <in.mp4> <out.gif> <crop_bottom_px> [--force]" >&2
  exit 2
}

SRC=${1:-}
OUT=${2:-}
BOTTOM=${3:-}
FORCE=${4:-}
[[ -n $SRC && -n $OUT && -n $BOTTOM ]] || usage

_TOP=95          # rows to drop from the top (Streamlit's Deploy toolbar)
_FPS=12          # a UI recording has no motion that needs more
_WIDTH=1600      # source is a retina capture; READMEs render this at ~900px
_COLORS=128      # the UI is near-monochrome, so half a palette is plenty

# `BOTTOM` reaches shell arithmetic, where a non-numeric value is *evaluated*,
# not rejected — `a[$(...)]` would run a command (red-team 2026-07-27 P1).
[[ $BOTTOM =~ ^[0-9]+$ ]] || { echo "crop_bottom_px must be a number, got: $BOTTOM" >&2; exit 2; }
BOTTOM=$((10#$BOTTOM))
((BOTTOM > _TOP)) || { echo "crop_bottom_px must exceed the top crop ($_TOP)" >&2; exit 2; }

command -v ffmpeg >/dev/null || { echo "ffmpeg not found on PATH" >&2; exit 1; }
[[ -f $SRC ]] || { echo "no such recording: $SRC" >&2; exit 2; }

# A typo in the output path would otherwise overwrite whatever it names — the
# `-y` below is unconditional (red-team 2026-07-27 P2).
[[ $OUT == *.gif ]] || { echo "output must be a .gif, got: $OUT" >&2; exit 2; }
if [[ -e $OUT && $FORCE != "--force" ]]; then
  echo "$OUT exists; pass --force to replace it" >&2
  exit 2
fi

SRC_HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$SRC")
((BOTTOM <= SRC_HEIGHT)) || {
  echo "crop_bottom_px ($BOTTOM) exceeds the recording's height ($SRC_HEIGHT)" >&2
  exit 2
}

HEIGHT=$((BOTTOM - _TOP))
FILTERS="crop=iw:${HEIGHT}:0:${_TOP},fps=${_FPS},scale=${_WIDTH}:-1:flags=lanczos"

mkdir -p "$(dirname "$OUT")"
TMP=$(mktemp -t demo-gif).gif
trap 'rm -f "$TMP"' EXIT

ffmpeg -v error -i "$SRC" \
  -vf "${FILTERS},split[a][b];[a]palettegen=max_colors=${_COLORS}:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 "$TMP" -y
mv "$TMP" "$OUT"   # written atomically: a failed run leaves the old GIF intact

printf '%s  %s  (ffmpeg %s)\n' \
  "$(du -h "$OUT" | cut -f1)" "$OUT" "$(ffmpeg -version | head -1 | awk '{print $3}')"
