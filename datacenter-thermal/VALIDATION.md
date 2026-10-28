# Validation — 27 October 2026

## Tested locally

- Windows x64; Python 3.14; GNU C++ 14.2 (Code::Blocks MinGW-w64).
- Release CMake build: CPU + OpenMP, with floating-point contraction disabled.
- All **11 automated tests passed** (`python -m unittest discover -s tests -v`).
- Independent Python equation reference checks unequal corner temperatures,
  edge neighbor counts, hash-driven workload drift and ambient adjustment.
- Full CPU/OpenMP fields and all statistics agree after 75 steps on 1, 2, 17 and
  64-wide grids. Separate tests check throttling, duplicate edits, invalid inputs,
  presets, rectangle updates and keeping live state unchanged by benchmarking.
- Both JavaScript files passed `node --check`; Python files compiled successfully.
- Browser checks: both pages render; rectangle drag selected 105 racks; Shift-click
  added a 106th; batch +10 °C updated all 106; Apply and Step updated temperatures,
  hotspot counts and statistics. Local Chart.js loaded and rendered the charts.
- The default five-grid, 100-step benchmark completed through the browser with
  8 OpenMP threads. CPU/OpenMP maximum-temperature difference was **0.0 °C**
  for every grid. CUDA was explicitly skipped.

## Measured benchmark

Wall milliseconds **per step**, excluding warm-up, creation and transfers.
One run; these are evidence from this machine, not promised performance.
Raw timing, settings, statistics and verification are in `benchmark-results.json`.

| Grid | CPU ms | OpenMP ms | OpenMP speedup | Max-temperature difference |
|---|---:|---:|---:|---:|
| 128 × 128 | 0.1773 | 0.3223 | 0.55× | 0.0 °C |
| 256 × 256 | 0.6827 | 0.4483 | 1.52× | 0.0 °C |
| 512 × 512 | 2.4821 | 0.7643 | 3.25× | 0.0 °C |
| 1024 × 1024 | 9.1899 | 2.9330 | 3.13× | 0.0 °C |
| 2048 × 2048 | 39.3172 | 9.1367 | 4.30× | 0.0 °C |

## Demo recovery check

On 64 × 64, rows/columns 26–37 inclusive were set to 80 °C, workload 100%,
cooling 5%. After 12 steps: max 91.279 °C, 96 hotspots. Setting only cooling to
100% and advancing 80 steps produced max 78.351 °C and **zero hotspots**.

## Not verified on this machine

CUDA compilation and execution, tiled/global CUDA agreement, CUDA event timing,
and the Linux/MSVC build paths have **not** been run here. `nvidia-smi` detects
an RTX 4060 Laptop GPU, but `nvcc`/the CUDA Toolkit was not found. No CUDA speedup
or successful GPU execution is claimed. The test suite automatically exercises
both CUDA kernels when a CUDA-enabled library/device is available.
