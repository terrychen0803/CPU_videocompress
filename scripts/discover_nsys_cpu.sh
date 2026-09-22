#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <DEVICE_NAME>"
  exit 1
fi

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

DEVICE="$1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$ROOT/runs/$DEVICE/environment/nsys_discovery"
mkdir -p "$OUT_DIR"

NSYS="$(find_nsys)" || {
  echo "Nsight Systems CLI not found."
  echo "Set NSYS_BIN or install nsys."
  exit 1
}

echo "Using: $NSYS"

"$NSYS" --version > "$OUT_DIR/nsys_version.txt" 2>&1 || true
"$NSYS" status --environment > "$OUT_DIR/nsys_status_environment.txt" 2>&1 || true
"$NSYS" profile --cpu-core-events=help > "$OUT_DIR/cpu_core_events.txt" 2>&1 || true
"$NSYS" profile --os-events=help > "$OUT_DIR/os_events.txt" 2>&1 || true
"$NSYS" profile --cpu-metrics=help > "$OUT_DIR/cpu_metrics_help.txt" 2>&1 || true

cat /proc/sys/kernel/perf_event_paranoid > "$OUT_DIR/perf_event_paranoid.txt" 2>/dev/null || true

echo
echo "== Candidate CPU events =="
grep -Ei "cycle|instruction|branch|cache|fault|frequency|clock"   "$OUT_DIR/cpu_core_events.txt" "$OUT_DIR/os_events.txt" 2>/dev/null | head -n 80 || true

echo
echo "Discovery files:"
find "$OUT_DIR" -maxdepth 1 -type f -printf "  %f\n" | sort

echo
echo "IMPORTANT:"
echo "1. Verify that event IDs 1 and 2 correspond to CPU Cycles and Instructions Retired."
echo "2. Record any branch/cache event IDs shared by all target CPUs."
echo "3. Do not assume Intel and AMD expose the same extended event list."
echo "4. System-wide event sampling generally requires perf_event_paranoid <= 0 or equivalent privileges."
