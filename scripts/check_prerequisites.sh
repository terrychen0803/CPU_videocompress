#!/usr/bin/env bash
set -euo pipefail

missing=0

find_nsys() {
  if [[ -n "${NSYS_BIN:-}" && -x "${NSYS_BIN}" ]]; then
    printf '%s\n' "${NSYS_BIN}"
    return 0
  fi

  if command -v nsys >/dev/null 2>&1; then
    command -v nsys
    return 0
  fi

  local known="/opt/nvidia/nsight-systems-cli/2026.4.1/target-linux-x64/nsys"
  if [[ -x "$known" ]]; then
    printf '%s\n' "$known"
    return 0
  fi

  return 1
}

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
check_cmd python3

if NSYS="$(find_nsys)"; then
  echo "[OK] nsys: $NSYS"
else
  echo "[MISSING] nsys"
  echo "Set NSYS_BIN or install Nsight Systems CLI."
  missing=1
fi

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Install/fix the missing dependencies before collecting data."
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
  exit 1
fi

echo
echo "== Nsight Systems version =="
"$NSYS" --version

echo
echo "== Nsight Systems CPU profiling environment =="
set +e
"$NSYS" status --environment
status_rc=$?
set -e
if [[ "$status_rc" -ne 0 ]]; then
  echo "[WARN] nsys status --environment returned $status_rc"
fi

echo
echo "== perf_event_paranoid =="
PARANOID="$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo unknown)"
echo "$PARANOID"

if [[ "$PARANOID" =~ ^-?[0-9]+$ ]] && (( PARANOID > 0 )); then
  echo "[WARN] Nsight Systems system-wide CPU event sampling normally requires perf_event_paranoid <= 0 or equivalent privileges."
fi

echo
echo "== CPU core event discovery smoke test =="
set +e
"$NSYS" profile --cpu-core-events=help >/tmp/cpu_videocompress_nsys_events.log 2>&1
event_rc=$?
set -e
if [[ "$event_rc" -eq 0 ]]; then
  echo "[OK] CPU core event list is available."
  grep -Ei "cycle|instruction|branch|cache" /tmp/cpu_videocompress_nsys_events.log | head -n 30 || true
else
  echo "[WARN] Could not query CPU core events:"
  cat /tmp/cpu_videocompress_nsys_events.log
fi
rm -f /tmp/cpu_videocompress_nsys_events.log

echo
echo "== Versions =="
ffmpeg -version | head -n 1
python3 --version

echo
echo "Prerequisite check complete."
