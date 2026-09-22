# CPU Video Compression Runtime Prediction

This repository contains the first-stage data collection pipeline for the **CPU Compute-Bound** workload in the Pre-6G runtime/resource prediction study.

The representative workload is **FFmpeg software video encoding** using `libx264` and `libx265`. The primary profiler is now **NVIDIA Nsight Systems (`nsys`)**, so the CPU experiment follows the same tooling philosophy as the existing GPU workload experiments:

```text
Workload configuration
        |
        +--> Full baseline run (no profiler)
        |       -> ground-truth runtime / encoding FPS
        |
        +--> Short marker-free Nsight Systems run
                -> CPU event time series + scheduling activity
                -> behavior / temporal / periodic features
                -> runtime/FPS prediction
```

## 1. Pilot workload matrix

The first pilot uses one fixed video content and varies only:

- Resolution: 1080p / 1440p / 4K
- Codec: H.264 (`libx264`) / H.265 (`libx265`)
- Preset: fast / medium / slow

This gives:

```text
3 resolutions x 2 codecs x 3 presets = 18 workloads
```

Fixed parameters:

- FPS: 30
- CRF: 23
- Audio: disabled
- Threads: FFmpeg/encoder default
- Pixel format: yuv420p

Definitions are stored in `workloads/workloads.csv`.

## 2. Repository structure

```text
CPU_videocompress/
├── inputs/                       # generated input videos (not committed)
├── workloads/
│   └── workloads.csv
├── scripts/
│   ├── check_prerequisites.sh
│   ├── discover_nsys_cpu.sh
│   ├── generate_inputs.sh
│   ├── collect_environment.sh
│   ├── run_baseline.py
│   ├── run_dryrun_nsys.py        # PRIMARY dry-run collector
│   └── run_dryrun_perf.py        # legacy/reference collector only
├── analysis/
│   ├── README.md
│   └── inspect_nsys_sqlite.py
├── runs/
├── results/
├── requirements.txt
└── .gitignore
```

## 3. Why Nsight Systems can be used for the CPU experiment

On Linux, Nsight Systems uses the Linux perf subsystem for CPU profiling. The useful collection modes for this project are:

- CPU hardware event sampling: CPU cycles, instructions retired, and additional branch/cache events when supported by the target CPU.
- CPU context-switch tracing: scheduling activity for the FFmpeg process tree.
- Optional CPU IP/backtrace sampling for function-level analysis.
- OS events when exposed by the target platform.

The exact event list is **CPU dependent**. Intel and AMD systems must therefore be queried on each node before the full experiment.

For the first cross-CPU pilot, the primary common event pair is:

```text
CPU Cycles
Instructions Retired
```

which supports:

```text
IPC = Instructions Retired / CPU Cycles
```

Branch, branch-miss, cache-reference, cache-miss, page-fault, and frequency-related signals are added only when Nsight Systems reports them as supported on that node.

### Important limitation

Nsight Systems CPU hardware event sampling is collected **system-wide across CPU cores**, not directly attributed to an individual process/thread. Process-tree context-switch tracing is collected separately.

Therefore the first workload-characterization experiments should run on an otherwise quiet node. Later experiments with background loading can intentionally treat the system-wide signals as node-state features.

## 4. Prerequisites

Ubuntu/Linux is assumed.

FFmpeg:

```bash
sudo apt update
sudo apt install ffmpeg
```

Nsight Systems must already be installed. The scripts search in this order:

1. `NSYS_BIN` environment variable
2. `nsys` in `PATH`
3. `/opt/nvidia/nsight-systems-cli/2026.4.1/target-linux-x64/nsys`

For the known 2026.4.1 installation:

```bash
export NSYS_BIN=/opt/nvidia/nsight-systems-cli/2026.4.1/target-linux-x64/nsys
```

Create the Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Check the node:

```bash
bash scripts/check_prerequisites.sh
```

For system-wide hardware event sampling, Linux permissions usually need:

```bash
cat /proc/sys/kernel/perf_event_paranoid
```

to be `0` or lower, or equivalent privileges. Do not start the full dataset until `nsys status --environment` and a C01 dry run both succeed.

## 5. Discover CPU events on each node

Run once per CPU node:

```bash
bash scripts/discover_nsys_cpu.sh Intel_i7_13700K
```

or:

```bash
bash scripts/discover_nsys_cpu.sh Ryzen_9950X
```

The output is saved under:

```text
runs/<DEVICE>/environment/nsys_discovery/
├── nsys_version.txt
├── nsys_status_environment.txt
├── cpu_core_events.txt
├── os_events.txt
└── cpu_metrics_help.txt
```

Inspect `cpu_core_events.txt` before choosing additional events. Event IDs and availability can differ between Intel and AMD.

The default collector uses `1,2` as the initial CPU Cycles + Instructions Retired pair. Verify those IDs in the discovery output on every node before large-scale collection.

## 6. Generate pilot input videos

Default duration is 60 seconds:

```bash
bash scripts/generate_inputs.sh
```

For a 300-second source:

```bash
bash scripts/generate_inputs.sh 300
```

The script creates:

```text
inputs/input_1080p.mp4
inputs/input_1440p.mp4
inputs/input_4k.mp4
```

The three files contain the same synthetic `testsrc2` content at different resolutions. Scaling is completed before the benchmark, so resize work is not included in the measured encoding run.

## 7. Record each CPU node environment

Run once on each node:

```bash
bash scripts/collect_environment.sh Intel_i7_13700K
```

The environment record includes CPU, RAM, kernel, FFmpeg, Nsight Systems version/status, CPU event discovery, frequency-governor information, and storage metadata.

## 8. Ground-truth baseline collection

Baseline runs must not use Nsight Systems or any other profiler.

Test C01 first:

```bash
python scripts/run_baseline.py \
  --device Intel_i7_13700K \
  --repeats 3 \
  --only C01
```

Then run all 18:

```bash
python scripts/run_baseline.py \
  --device Intel_i7_13700K \
  --repeats 3
```

Each workload receives:

```text
runs/<DEVICE>/<WORKLOAD>/baseline_XX/
├── ffmpeg.log
└── summary.json

runs/<DEVICE>/<WORKLOAD>/baseline_summary.json
```

Ground truth is the median of the successful no-profiler runs.

## 9. Primary dry run: Nsight Systems

Default pilot settings:

- total profiling window: 35 s
- first 5 s marked as warm-up for later exclusion
- CPU event sampling interval: 100 ms
- context-switch scope: FFmpeg process tree
- CPU IP sampling: disabled by default to reduce overhead
- input looped so fast configurations do not terminate before the collection window
- CPU core events: `1,2` by default, subject to per-node verification
- output: `.nsys-rep` + SQLite export

Run C01:

```bash
python scripts/run_dryrun_nsys.py \
  --device Intel_i7_13700K \
  --only C01
```

If discovery shows additional event IDs that are supported and can be sampled together:

```bash
python scripts/run_dryrun_nsys.py \
  --device Intel_i7_13700K \
  --only C01 \
  --cpu-core-events 1,2,<branch-id>,<branch-miss-id>
```

Do not guess event IDs; use the discovery output.

Outputs:

```text
runs/<DEVICE>/<WORKLOAD>/dryrun_nsys_01/
├── profile.nsys-rep
├── profile.sqlite
├── ffmpeg.log
└── metadata.json
```

The SQLite schema can vary with Nsight Systems versions, so inspect the actual C01 export before implementing the final feature extractor:

```bash
python analysis/inspect_nsys_sqlite.py \
  runs/Intel_i7_13700K/C01/dryrun_nsys_01/profile.sqlite
```

## 10. Candidate features

The feature hierarchy is intentionally similar to the GPU project but does not assume that video encoding has a clean YOLO-like iteration period.

### Core behavior

```text
CPU cycles rate
instructions-retired rate
IPC
CPU scheduling / utilization behavior
context-switch behavior
```

### Additional node-supported events

When available:

```text
branches
branch misses
cache references
cache misses
page faults / selected OS events
frequency-related events or metrics
```

### Temporal features

For each time series after removing warm-up:

```text
mean
std
P10 / P50 / P90
coefficient of variation
trend
peak
burstiness
```

### Periodic/spectral features

Experimental:

```text
autocorrelation peak
dominant period
period confidence
FFT dominant frequency
spectral concentration
```

The planned ablation remains:

```text
Aggregate
vs.
Aggregate + Temporal
vs.
Aggregate + Temporal + Periodic
```

The purpose is to test whether a marker-free periodic signature helps CPU encoding prediction, not to assume that one must exist.

## 11. Recommended execution order

```text
1. git pull
2. check_prerequisites.sh
3. discover_nsys_cpu.sh <DEVICE>
4. generate_inputs.sh 60
5. collect_environment.sh <DEVICE>
6. C01 baseline x3
7. C01 Nsight Systems dry run
8. inspect profile.nsys-rep / profile.sqlite
9. confirm event availability and overhead
10. collect C01-C18 on node A
11. repeat on node B
12. implement feature extraction / period analysis
13. runtime/FPS prediction
```

Do not collect all 18 workloads until C01 has produced a valid `.nsys-rep`, SQLite export, and useful CPU event time series.
