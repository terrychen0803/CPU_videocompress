#!/usr/bin/env bash
set -euo pipefail

missing=0

check_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "[OK] $cmd: $(command -v "$cmd")"
  else
    echo "[MISSING] $cmd"
    missing=1
  fi
}

echo "== Commands =="
check_cmd ffmpeg
check_cmd ffprobe
check_cmd perf
check_cmd python3

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Install the missing dependencies before collecting data."
  exit 1
fi

echo
echo "== FFmpeg software encoders =="
encoders="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
for enc in libx264 libx265; do
  if grep -q "$enc" <<<"$encoders"; then
    echo "[OK] $enc"
  else
    echo "[MISSING] $enc"
    missing=1
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Required software encoders are missing."
  exit 1
fi

echo
echo "== perf permission smoke test =="
set +e
perf stat -e cycles,instructions -- sleep 0.2 >/dev/null 2>/tmp/cpu_videocompress_perf_test.log
rc=$?
set -e

if [[ "$rc" -eq 0 ]]; then
  echo "[OK] perf hardware counters are accessible"
else
  echo "[WARN] perf test failed (exit=$rc)"
  cat /tmp/cpu_videocompress_perf_test.log
  echo
  echo "Check: cat /proc/sys/kernel/perf_event_paranoid"
fi

rm -f /tmp/cpu_videocompress_perf_test.log

echo
echo "== Versions =="
ffmpeg -version | head -n 1
perf --version
python3 --version

echo
echo "Prerequisite check complete."
