#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/inputs"

DURATION="${1:-60}"
FPS="${FPS:-30}"
CRF="${SOURCE_CRF:-18}"
PRESET="${SOURCE_PRESET:-veryfast}"

mkdir -p "$OUT_DIR"

echo "Generating deterministic pilot inputs"
echo "duration=${DURATION}s fps=${FPS} source_crf=${CRF} preset=${PRESET}"

ffmpeg -y -hide_banner   -f lavfi   -i "testsrc2=size=3840x2160:rate=${FPS}:duration=${DURATION}"   -an   -c:v libx264   -preset "$PRESET"   -crf "$CRF"   -pix_fmt yuv420p   "$OUT_DIR/input_4k.mp4"

ffmpeg -y -hide_banner   -i "$OUT_DIR/input_4k.mp4"   -vf "scale=2560:1440"   -an   -c:v libx264   -preset "$PRESET"   -crf "$CRF"   -pix_fmt yuv420p   "$OUT_DIR/input_1440p.mp4"

ffmpeg -y -hide_banner   -i "$OUT_DIR/input_4k.mp4"   -vf "scale=1920:1080"   -an   -c:v libx264   -preset "$PRESET"   -crf "$CRF"   -pix_fmt yuv420p   "$OUT_DIR/input_1080p.mp4"

echo
echo "Generated files:"
ls -lh "$OUT_DIR"/input_*.mp4

echo
echo "Probe summary:"
for f in "$OUT_DIR"/input_1080p.mp4 "$OUT_DIR"/input_1440p.mp4 "$OUT_DIR"/input_4k.mp4; do
  echo "--- $(basename "$f") ---"
  ffprobe -v error     -select_streams v:0     -show_entries stream=width,height,avg_frame_rate,nb_frames,duration     -of default=noprint_wrappers=1     "$f"
done
