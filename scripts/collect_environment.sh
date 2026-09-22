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
OUT_DIR="$ROOT/runs/$DEVICE/environment"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/environment_${STAMP}.txt"
NSYS="$(find_nsys || true)"

{
  echo "# CPU Video Compression Experiment Environment"
  echo "timestamp_utc=$STAMP"
  echo "device=$DEVICE"
  echo

  echo "## uname"
  uname -a
  echo

  echo "## lscpu"
  lscpu
  echo

  echo "## memory"
  free -h
  echo

  echo "## ffmpeg"
  ffmpeg -version
  echo

  echo "## python"
  python3 --version
  echo

  echo "## perf_event_paranoid"
  cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || true
  echo

  echo "## Nsight Systems"
  if [[ -n "$NSYS" ]]; then
    echo "nsys_path=$NSYS"
    "$NSYS" --version 2>&1 || true
    echo
    echo "### nsys status --environment"
    "$NSYS" status --environment 2>&1 || true
  else
    echo "Nsight Systems CLI not found"
  fi
  echo

  echo "## CPU frequency governors"
  grep -H . /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u || true
  echo

  echo "## CPU frequency limits (kHz)"
  for f in     /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq     /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq     /sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq     /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq; do
    if [[ -r "$f" ]]; then
      echo "$f=$(cat "$f")"
    fi
  done
  echo

  echo "## storage"
  lsblk -o NAME,TYPE,SIZE,ROTA,MODEL,MOUNTPOINTS 2>/dev/null || true
  echo

  echo "## NUMA"
  if command -v numactl >/dev/null 2>&1; then
    numactl --hardware
  else
    echo "numactl not installed"
  fi
} > "$OUT"

if lscpu -J >/dev/null 2>&1; then
  lscpu -J > "$OUT_DIR/lscpu_${STAMP}.json"
fi

if [[ -n "$NSYS" ]]; then
  "$NSYS" profile --cpu-core-events=help > "$OUT_DIR/nsys_cpu_core_events_${STAMP}.txt" 2>&1 || true
  "$NSYS" profile --os-events=help > "$OUT_DIR/nsys_os_events_${STAMP}.txt" 2>&1 || true
  "$NSYS" profile --cpu-metrics=help > "$OUT_DIR/nsys_cpu_metrics_help_${STAMP}.txt" 2>&1 || true
fi

cp "$OUT" "$OUT_DIR/environment_latest.txt"

echo "Environment saved to:"
echo "  $OUT"
