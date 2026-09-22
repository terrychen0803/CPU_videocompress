#!/usr/bin/env python3
import argparse
import csv
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_CSV = ROOT / "workloads" / "workloads.csv"
INPUT_DIR = ROOT / "inputs"
RUNS_DIR = ROOT / "runs"


def parse_args():
    p = argparse.ArgumentParser(description="Collect no-profiler FFmpeg ground truth.")
    p.add_argument("--device", required=True, help="Stable device name used under runs/.")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--only", help="Run one workload ID, e.g. C01.")
    p.add_argument("--cooldown", type=float, default=10.0, help="Seconds between runs.")
    p.add_argument("--force", action="store_true", help="Overwrite completed run directories.")
    return p.parse_args()


def load_workloads():
    with WORKLOAD_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fps_from_fraction(value):
    if not value or value == "0/0":
        return None
    return float(Fraction(value))


def probe_video(path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=nb_frames,avg_frame_rate,r_frame_rate,duration",
        "-of", "json",
        str(path),
    ]
    data = json.loads(subprocess.check_output(cmd, text=True))
    stream = data["streams"][0]

    fps = fps_from_fraction(stream.get("avg_frame_rate")) or fps_from_fraction(stream.get("r_frame_rate"))
    duration = float(stream["duration"]) if stream.get("duration") not in (None, "N/A") else None

    frames = None
    if stream.get("nb_frames") not in (None, "N/A"):
        frames = int(stream["nb_frames"])
    elif duration is not None and fps is not None:
        frames = round(duration * fps)

    return {"input_fps": fps, "input_duration_sec": duration, "input_frames": frames}


def ffmpeg_command(w, input_path):
    return [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-nostats",
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


def run_one(args, w, repeat_idx):
    wid = w["workload_id"]
    input_path = INPUT_DIR / w["input_file"]
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input: {input_path}. Run scripts/generate_inputs.sh first.")

    run_dir = RUNS_DIR / args.device / wid / f"baseline_{repeat_idx:02d}"
    summary_path = run_dir / "summary.json"

    if summary_path.exists() and not args.force:
        existing = json.loads(summary_path.read_text(encoding="utf-8"))
        if existing.get("status") == "ok":
            print(f"[SKIP] {wid} baseline_{repeat_idx:02d}")
            return existing

    run_dir.mkdir(parents=True, exist_ok=True)
    probe = probe_video(input_path)
    cmd = ffmpeg_command(w, input_path)

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    with (run_dir / "ffmpeg.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=log)
    runtime = time.perf_counter() - t0

    frames = probe["input_frames"]
    encoding_fps = (frames / runtime) if frames else None

    summary = {
        "status": "ok" if proc.returncode == 0 else "failed",
        "timestamp_utc": started,
        "device": args.device,
        "workload_id": wid,
        "input_file": w["input_file"],
        "resolution": w["resolution"],
        "codec": w["codec"],
        "preset": w["preset"],
        "crf": int(w["crf"]),
        "configured_fps": float(w["fps"]),
        **probe,
        "runtime_sec": runtime,
        "encoding_fps": encoding_fps,
        "returncode": proc.returncode,
        "profiling_enabled": False,
        "command": cmd,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(f"{wid} failed. See {run_dir / 'ffmpeg.log'}")

    print(f"[OK] {wid} baseline_{repeat_idx:02d}: {runtime:.3f}s, {encoding_fps:.2f} FPS")
    return summary


def write_aggregate(device, wid):
    workload_dir = RUNS_DIR / device / wid
    summaries = []
    for p in sorted(workload_dir.glob("baseline_*/summary.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("status") == "ok":
            summaries.append(data)

    if not summaries:
        return

    runtimes = [x["runtime_sec"] for x in summaries]
    fps_values = [x["encoding_fps"] for x in summaries if x.get("encoding_fps") is not None]

    out = {
        "device": device,
        "workload_id": wid,
        "successful_repeats": len(summaries),
        "runtime_sec_values": runtimes,
        "runtime_sec_median": statistics.median(runtimes),
        "encoding_fps_values": fps_values,
        "encoding_fps_median": statistics.median(fps_values) if fps_values else None,
        "ground_truth_definition": "median of successful no-profiler baseline runs",
    }
    (workload_dir / "baseline_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


def main():
    args = parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be >= 1")

    workloads = load_workloads()
    if args.only:
        workloads = [w for w in workloads if w["workload_id"] == args.only]
        if not workloads:
            raise SystemExit(f"Unknown workload ID: {args.only}")

    for w in workloads:
        for repeat_idx in range(1, args.repeats + 1):
            run_one(args, w, repeat_idx)
            if args.cooldown > 0:
                time.sleep(args.cooldown)
        write_aggregate(args.device, w["workload_id"])

    print("Baseline collection complete.")


if __name__ == "__main__":
    main()
