#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_CSV = ROOT / "workloads" / "workloads.csv"
INPUT_DIR = ROOT / "inputs"
RUNS_DIR = ROOT / "runs"

KNOWN_NSYS = Path("/opt/nvidia/nsight-systems-cli/2026.4.1/target-linux-x64/nsys")


def find_nsys():
    env = os.environ.get("NSYS_BIN")
    if env and Path(env).is_file():
        return str(Path(env).resolve())

    in_path = shutil.which("nsys")
    if in_path:
        return in_path

    if KNOWN_NSYS.is_file():
        return str(KNOWN_NSYS)

    raise FileNotFoundError(
        "Nsight Systems CLI not found. Set NSYS_BIN or install nsys."
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="Collect marker-free FFmpeg CPU dry runs with NVIDIA Nsight Systems."
    )
    p.add_argument("--device", required=True)
    p.add_argument("--only", help="Run one workload ID, e.g. C01.")
    p.add_argument("--repeat-id", type=int, default=1)
    p.add_argument("--wall-seconds", type=float, default=35.0)
    p.add_argument("--warmup-seconds", type=float, default=5.0)
    p.add_argument("--event-sampling-interval-ms", type=int, default=100)
    p.add_argument(
        "--cpu-core-events",
        default="1,2",
        help=(
            "Comma-separated IDs reported by 'nsys profile --cpu-core-events=help'. "
            "Default 1,2 is intended for CPU Cycles + Instructions Retired and must "
            "be verified on each node."
        ),
    )
    p.add_argument(
        "--sample-mode",
        choices=["none", "process-tree"],
        default="none",
        help="Optional CPU IP sampling. Default none keeps collection lightweight.",
    )
    p.add_argument(
        "--no-event-sampling",
        action="store_true",
        help="Disable system-wide CPU hardware event sampling; useful for permission debugging.",
    )
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
        "-stream_loop",
        "-1",
        "-i",
        str(input_path),
        "-map",
        "0:v:0",
        "-an",
        "-c:v",
        w["codec"],
        "-preset",
        w["preset"],
        "-crf",
        str(w["crf"]),
        "-pix_fmt",
        "yuv420p",
        "-f",
        "null",
        "-",
    ]


def command_output(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def read_paranoid():
    path = Path("/proc/sys/kernel/perf_event_paranoid")
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def run_one(args, w, nsys):
    wid = w["workload_id"]
    input_path = INPUT_DIR / w["input_file"]
    if not input_path.exists():
        raise FileNotFoundError(
            f"Missing input: {input_path}. Run scripts/generate_inputs.sh first."
        )

    run_dir = RUNS_DIR / args.device / wid / f"dryrun_nsys_{args.repeat_id:02d}"
    metadata_path = run_dir / "metadata.json"

    if metadata_path.exists() and not args.force:
        old = json.loads(metadata_path.read_text(encoding="utf-8"))
        if old.get("status") == "ok":
            print(f"[SKIP] {wid} dryrun_nsys_{args.repeat_id:02d}")
            return

    run_dir.mkdir(parents=True, exist_ok=True)
    report_prefix = run_dir / "profile"
    ffmpeg_log = run_dir / "ffmpeg.log"
    nsys_log = run_dir / "nsys.log"

    ffmpeg_cmd = ffmpeg_command(w, input_path)

    timed_cmd = [
        "timeout",
        "--signal=INT",
        "--kill-after=5",
        f"{args.wall_seconds}s",
        *ffmpeg_cmd,
    ]

    nsys_cmd = [
        nsys,
        "profile",
        "--force-overwrite=true",
        "--trace=none",
        f"--sample={args.sample_mode}",
        "--cpuctxsw=process-tree",
        "--show-source-info=false",
        "--export=sqlite",
        "-o",
        str(report_prefix),
    ]

    if not args.no_event_sampling:
        nsys_cmd += [
            "--event-sample=system-wide",
            f"--cpu-core-events={args.cpu_core_events}",
            f"--event-sampling-interval={args.event_sampling_interval_ms}",
        ]

    nsys_cmd += timed_cmd

    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    with ffmpeg_log.open("w", encoding="utf-8") as app_log,          nsys_log.open("w", encoding="utf-8") as profiler_log:
        proc = subprocess.run(
            nsys_cmd,
            stdout=profiler_log,
            stderr=app_log,
        )

    elapsed = time.perf_counter() - t0

    report = run_dir / "profile.nsys-rep"
    sqlite = run_dir / "profile.sqlite"
    ok = report.exists() and report.stat().st_size > 0

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
        "profiler": "NVIDIA Nsight Systems",
        "nsys_path": nsys,
        "nsys_version": command_output([nsys, "--version"]),
        "wall_seconds": args.wall_seconds,
        "warmup_seconds_to_discard": args.warmup_seconds,
        "event_sampling_enabled": not args.no_event_sampling,
        "event_sampling_scope": "system-wide" if not args.no_event_sampling else None,
        "event_sampling_interval_ms": (
            args.event_sampling_interval_ms if not args.no_event_sampling else None
        ),
        "cpu_core_events": (
            args.cpu_core_events if not args.no_event_sampling else None
        ),
        "cpu_ip_sampling": args.sample_mode,
        "context_switch_scope": "process-tree",
        "perf_event_paranoid": read_paranoid(),
        "input_looped": True,
        "elapsed_wall_sec_including_report_generation": elapsed,
        "nsys_returncode": proc.returncode,
        "report_path": str(report.relative_to(ROOT)) if report.exists() else None,
        "sqlite_path": str(sqlite.relative_to(ROOT)) if sqlite.exists() else None,
        "note": (
            "CPU hardware event samples are system-wide, while context switches are "
            "collected for the launched process tree. Discard the initial warm-up "
            "region during feature extraction."
        ),
        "command": nsys_cmd,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    if not ok:
        raise RuntimeError(
            f"{wid} Nsight Systems collection failed or no .nsys-rep was generated. "
            f"See {nsys_log} and {ffmpeg_log}."
        )

    print(f"[OK] {wid}: {report}")
    if sqlite.exists():
        print(f"     SQLite: {sqlite}")
    else:
        print("     [WARN] SQLite export was not generated; inspect nsys.log.")


def main():
    args = parse_args()

    if args.repeat_id < 1:
        raise SystemExit("--repeat-id must be >= 1")
    if args.wall_seconds <= 0:
        raise SystemExit("--wall-seconds must be > 0")
    if args.warmup_seconds < 0 or args.warmup_seconds >= args.wall_seconds:
        raise SystemExit("--warmup-seconds must be >= 0 and < --wall-seconds")
    if args.event_sampling_interval_ms < 1 or args.event_sampling_interval_ms > 1000:
        raise SystemExit("--event-sampling-interval-ms must be between 1 and 1000")

    nsys = find_nsys()

    if not args.no_event_sampling:
        paranoid = read_paranoid()
        if paranoid is not None and paranoid > 0:
            print(
                f"[WARN] perf_event_paranoid={paranoid}. Nsight Systems system-wide "
                "CPU event sampling generally requires <= 0 or equivalent privileges."
            )

    workloads = load_workloads()
    if args.only:
        workloads = [w for w in workloads if w["workload_id"] == args.only]
        if not workloads:
            raise SystemExit(f"Unknown workload ID: {args.only}")

    for w in workloads:
        run_one(args, w, nsys)

    print("Nsight Systems dry-run collection complete.")


if __name__ == "__main__":
    main()
