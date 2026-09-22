#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_CSV = ROOT / "workloads" / "workloads.csv"
INPUT_DIR = ROOT / "inputs"
RUNS_DIR = ROOT / "runs"

DEFAULT_EVENTS = [
    "task-clock",
    "cycles",
    "instructions",
    "branches",
    "branch-misses",
    "cache-references",
    "cache-misses",
    "context-switches",
    "page-faults",
]


def parse_args():
    p = argparse.ArgumentParser(description="Collect short marker-free FFmpeg CPU perf traces.")
    p.add_argument("--device", required=True)
    p.add_argument("--only", help="Run one workload ID, e.g. C01.")
    p.add_argument("--repeat-id", type=int, default=1)
    p.add_argument("--interval-ms", type=int, default=100)
    p.add_argument("--wall-seconds", type=float, default=35.0)
    p.add_argument("--warmup-seconds", type=float, default=5.0,
                   help="Metadata only; analysis should discard this initial region.")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def load_workloads():
    with WORKLOAD_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ffmpeg_command(w, input_path):
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-nostats",
        "-stream_loop", "-1",
        "-i", str(input_path),
        "-map", "0:v:0",
        "-an",
        "-c:v", w["codec"],
        "-preset", w["preset"],
        "-crf", str(w["crf"]),
        "-pix_fmt", "yuv420p",
        "-f", "null",
        "-",
    ]


def run_one(args, w):
    wid = w["workload_id"]
    input_path = INPUT_DIR / w["input_file"]
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input: {input_path}. Run scripts/generate_inputs.sh first.")

    run_dir = RUNS_DIR / args.device / wid / f"dryrun_perf_{args.repeat_id:02d}"
    metadata_path = run_dir / "metadata.json"

    if metadata_path.exists() and not args.force:
        old = json.loads(metadata_path.read_text(encoding="utf-8"))
        if old.get("status") == "ok":
            print(f"[SKIP] {wid} dryrun_perf_{args.repeat_id:02d}")
            return

    run_dir.mkdir(parents=True, exist_ok=True)
    perf_csv = run_dir / "perf.csv"
    ffmpeg_log = run_dir / "ffmpeg.log"

    ffmpeg_cmd = ffmpeg_command(w, input_path)
    timed_cmd = [
        "timeout",
        "--signal=INT",
        "--kill-after=5",
        f"{args.wall_seconds}s",
        *ffmpeg_cmd,
    ]

    perf_cmd = [
        "perf", "stat",
        "-I", str(args.interval_ms),
        "-x", ",",
        "--no-big-num",
        "-o", str(perf_csv),
        "-e", ",".join(DEFAULT_EVENTS),
        "--",
        *timed_cmd,
    ]

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    with ffmpeg_log.open("w", encoding="utf-8") as log:
        proc = subprocess.run(perf_cmd, stdout=subprocess.DEVNULL, stderr=log)
    elapsed = time.perf_counter() - t0

    expected = proc.returncode in (0, 124, 130)
    ok = expected and perf_csv.exists() and perf_csv.stat().st_size > 0

    metadata = {
        "status": "ok" if ok else "failed",
        "timestamp_utc": started,
        "device": args.device,
        "workload_id": wid,
        "input_file": w["input_file"],
        "resolution": w["resolution"],
        "codec": w["codec"],
        "preset": w["preset"],
        "crf": int(w["crf"]),
        "configured_fps": float(w["fps"]),
        "profiler": "perf stat interval mode",
        "interval_ms": args.interval_ms,
        "wall_seconds": args.wall_seconds,
        "warmup_seconds_to_discard": args.warmup_seconds,
        "events": DEFAULT_EVENTS,
        "elapsed_wall_sec": elapsed,
        "returncode": proc.returncode,
        "input_looped": True,
        "note": "Discard the initial warmup_seconds_to_discard seconds during feature extraction.",
        "command": perf_cmd,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if not ok:
        raise RuntimeError(f"{wid} perf collection failed. See {ffmpeg_log} and {perf_csv}.")

    print(f"[OK] {wid}: perf trace -> {perf_csv}")


def main():
    args = parse_args()
    if args.interval_ms <= 0:
        raise SystemExit("--interval-ms must be > 0")
    if args.wall_seconds <= 0:
        raise SystemExit("--wall-seconds must be > 0")
    if args.warmup_seconds < 0 or args.warmup_seconds >= args.wall_seconds:
        raise SystemExit("--warmup-seconds must be >= 0 and < --wall-seconds")

    workloads = load_workloads()
    if args.only:
        workloads = [w for w in workloads if w["workload_id"] == args.only]
        if not workloads:
            raise SystemExit(f"Unknown workload ID: {args.only}")

    for w in workloads:
        run_one(args, w)

    print("Dry-run perf collection complete.")


if __name__ == "__main__":
    main()
