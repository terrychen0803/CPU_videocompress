# Analysis plan

The primary dry-run source is now **Nsight Systems**. Feature extraction should be implemented only after validating the actual `profile.sqlite` schema and event availability on both CPU nodes.

## Raw data sources

Each dry-run collection should retain:

```text
profile.nsys-rep     <- canonical Nsight Systems report
profile.sqlite       <- machine-readable export
metadata.json        <- workload + collection settings
ffmpeg.log           <- application log, oracle/debug only
```

The `.nsys-rep` file is the canonical raw artifact. SQLite is used for research feature extraction.

CPU hardware event sampling is system-wide. Process-tree scheduling/context-switch data is separate. Keep the pilot nodes otherwise quiet when interpreting CPU event rates as workload behavior.

## Feature families

### A. Core CPU behavior

Common target signals:

- CPU Cycles
- Instructions Retired
- IPC = Instructions / Cycles
- FFmpeg process-tree scheduling activity
- context-switch behavior

Additional branch/cache/OS events are used only when `nsys profile --cpu-core-events=help` or `--os-events=help` confirms support on the target CPU.

### B. Aggregate features

For each collected signal after warm-up removal:

- mean
- median
- standard deviation
- P10 / P50 / P90
- min / max
- coefficient of variation

Derived ratios, when both source signals are valid:

```text
IPC = instructions / cycles
branch_miss_rate = branch_misses / branches
cache_miss_rate = cache_misses / cache_references
```

Do not synthesize unsupported counters as zero. Missing/unsupported signals should be marked unavailable.

### C. Temporal features

- trend / slope
- window-to-window variance
- peak activity
- burstiness
- active fraction
- scheduling stability

### D. Periodic / spectral features

These are experimental, not assumed:

- autocorrelation peaks
- dominant period
- period confidence
- FFT dominant frequency
- spectral concentration / repeatability

The planned ablation is:

```text
Aggregate
vs.
Aggregate + Temporal
vs.
Aggregate + Temporal + Periodic
```

The objective is to test whether marker-free periodic features improve FFmpeg performance prediction.

## Ground truth

Use only `baseline_summary.json` generated from no-profiler runs.

Primary labels:

- median full encoding runtime
- median encoding FPS

Nsight Systems profiled runtime must not be used as ground truth.

## Warm-up

The default dry run records 35 seconds and marks the first 5 seconds as warm-up.

Feature extraction should use only the post-warm-up region.

## Inspect the real SQLite schema first

Nsight Systems export schemas can differ by release and collection configuration.

After collecting C01:

```bash
python analysis/inspect_nsys_sqlite.py \
  runs/<DEVICE>/C01/dryrun_nsys_01/profile.sqlite
```

Use the resulting table/column inventory to implement the final time-series extractor rather than hard-coding an old Nsight Systems SQLite schema.

## Oracle/application logs

FFmpeg frame/FPS progress can be used for offline validation only. It should not be required by the production feature pipeline if the objective remains marker-free profiling.
