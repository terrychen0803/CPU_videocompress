# Analysis plan

The collection pipeline is implemented first. Feature extraction and modeling should be added only after validating the raw `perf.csv` format on both CPU nodes.

## Feature families

### A. Aggregate features

- task-clock mean / median
- cycles mean
- instructions mean
- IPC = instructions / cycles
- branch miss rate = branch-misses / branches
- cache miss rate = cache-misses / cache-references

### B. Temporal features

After removing warm-up:

- mean
- standard deviation
- P10 / P50 / P90
- coefficient of variation
- trend / slope
- peak
- burstiness / active fraction where meaningful

### C. Periodic / spectral features

These are experimental rather than assumed:

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

This directly tests whether periodic features add predictive value for FFmpeg CPU encoding.

## Ground truth

Use only `baseline_summary.json` from no-profiler runs.

Primary labels:

- median full encoding runtime
- median encoding FPS

Profiler-inflated runtime must not be used as ground truth.

## Oracle/application logs

FFmpeg progress information may be used for offline validation, but application-derived frame/FPS markers should not be required by the production feature pipeline if the goal remains marker-free profiling.
