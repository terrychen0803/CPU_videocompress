# CPU Video Compression Runtime Prediction

This repository contains the first-stage data collection pipeline for the **CPU Compute-Bound** workload in the Pre-6G runtime/resource prediction study.

The representative workload is **FFmpeg software video encoding** using `libx264` and `libx265`. The research workflow follows the same high-level idea used in the GPU workload experiments:

```text
Workload configuration
        |
        +--> Full baseline run (no profiler)
        |       -> Ground truth runtime / encoding FPS
        |
        +--> Short marker-free CPU profiling run
                -> perf counter time series
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

Fixed parameters for the first stage:

- FPS: 30
- CRF: 23
- Audio: disabled
- Threads: FFmpeg/encoder default
- Pixel format: yuv420p

The workload definitions are stored in `workloads/workloads.csv`.

## 2. Repository structure

```text
CPU_videocompress/
├── inputs/                     # generated input videos (not committed)
├── workloads/
│   └── workloads.csv
├── scripts/
│   ├── check_prerequisites.sh
│   ├── generate_inputs.sh
│   ├── collect_environment.sh
│   ├── run_baseline.py
│   └── run_dryrun_perf.py
├── analysis/
│   └── README.md
├── runs/                       # experiment outputs (not committed)
├── results/                    # analysis outputs (not committed)
├── requirements.txt
└── .gitignore
```

## 3. Prerequisites

Ubuntu/Linux is assumed.

```bash
sudo apt update
sudo apt install ffmpeg linux-tools-common linux-tools-generic
sudo apt install linux-tools-$(uname -r)
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

A quick perf permission test is also included. If perf reports a permission error, inspect:

```bash
cat /proc/sys/kernel/perf_event_paranoid
```

## 4. Generate pilot input videos

For initial pipeline validation, generate a deterministic FFmpeg `testsrc2` video set.

Default duration is 60 seconds:

```bash
bash scripts/generate_inputs.sh
```

Or choose another duration, for example 300 seconds:

```bash
bash scripts/generate_inputs.sh 300
```

The script creates:

```text
inputs/input_1080p.mp4
inputs/input_1440p.mp4
inputs/input_4k.mp4
```

These files are intentionally ignored by git.

> Note: the pilot source is H.264-compressed, so the measured application includes input decoding plus software encoding. This is acceptable for pipeline validation and end-to-end video compression benchmarking. If a later experiment needs to isolate encoder-only cost, use a raw/lossless source and account for the much larger storage requirement.

## 5. Record each CPU node environment

Run once on each node:

```bash
bash scripts/collect_environment.sh Intel_i7_13700K
```

or:

```bash
bash scripts/collect_environment.sh Ryzen_9950X
```

The script stores CPU, memory, kernel, FFmpeg, perf, frequency-governor, and storage information under:

```text
runs/<DEVICE>/environment/
```

## 6. Ground-truth baseline collection

Baseline runs must **not** use perf/profiling.

Run all 18 workloads with three repeats:

```bash
source .venv/bin/activate

python scripts/run_baseline.py \
  --device Intel_i7_13700K \
  --repeats 3
```

Test only C01 first:

```bash
python scripts/run_baseline.py \
  --device Intel_i7_13700K \
  --repeats 3 \
  --only C01
```

Each run stores:

```text
runs/<DEVICE>/<WORKLOAD>/baseline_XX/
├── ffmpeg.log
└── summary.json
```

and each workload receives:

```text
runs/<DEVICE>/<WORKLOAD>/baseline_summary.json
```

with median runtime and median encoding FPS.

## 7. Short CPU dry-run profiling

The first-stage profiler uses Linux `perf stat` with interval sampling.

Default settings:

- interval: 100 ms
- wall-clock profiling window: 35 s
- warm-up portion excluded later: first 5 s
- input is looped during the profiling run so fast encoders do not terminate before the profiling window

Example:

```bash
python scripts/run_dryrun_perf.py \
  --device Intel_i7_13700K \
  --only C01
```

Run all workloads:

```bash
python scripts/run_dryrun_perf.py \
  --device Intel_i7_13700K
```

Raw counters include:

- task-clock
- cycles
- instructions
- branches
- branch-misses
- cache-references
- cache-misses
- context-switches
- page-faults

Outputs:

```text
runs/<DEVICE>/<WORKLOAD>/dryrun_perf_01/
├── perf.csv
├── ffmpeg.log
└── metadata.json
```

## 8. Planned feature analysis

Do **not** assume that FFmpeg has the same clean single iteration period as YOLO training.

The planned ablation is:

1. Aggregate CPU counter features
2. Aggregate + temporal features
3. Aggregate + temporal + periodic/spectral features

Candidate derived features:

```text
IPC = instructions / cycles
branch_miss_rate = branch-misses / branches
cache_miss_rate = cache-misses / cache-references

mean / std / P10 / P50 / P90 / CV / trend
autocorrelation peak
dominant period
FFT dominant frequency
period confidence
```

This allows the study to test whether marker-free periodic behavior actually improves CPU video-encoding runtime prediction, rather than assuming that it must.

## 9. Recommended execution order

```text
1. check_prerequisites.sh
2. generate_inputs.sh
3. collect_environment.sh
4. C01 baseline x3
5. C01 dry-run perf
6. inspect summary.json / perf.csv
7. collect C01-C18 on node A
8. repeat on node B
9. feature extraction and periodicity analysis
10. runtime/FPS prediction
```

## 10. Next dataset expansion

After the 18-workload pilot is stable, add real video contents with different complexity:

- low motion
- medium motion
- high motion / high detail

The expanded dataset can then test whether the predictor generalizes across unseen video content rather than only across resolution/codec/preset configurations.
