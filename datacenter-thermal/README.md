# Parallel Data Center Thermal Simulation and Hotspot Analysis using CUDA

A small P-CAP university project: treat a data center as an N × N grid of racks,
change multiple racks together, observe diffusion and throttling, and measure the
same model on sequential CPU, OpenMP, and CUDA. The browser uses plain HTML/CSS/JS
and a locally bundled Chart.js; Flask calls a C++ shared library through `ctypes`.

This is an educational **digital twin**, not a calibrated engineering or CFD
model. A step is one discrete simulation iteration, not one physical second.

## Quick start on this Windows workspace

CPU and OpenMP have already been built in `build/`, and Flask is installed in
`.venv/`. From PowerShell:

```powershell
cd C:\Users\Saarthak\Desktop\datacenter_final\datacenter-thermal
.\run.ps1
```

Open <http://127.0.0.1:5000>. Stop with Ctrl+C. `run.ps1 -Build` rebuilds the
CPU/OpenMP library first. The script detects the Code::Blocks 64-bit toolchain
on this machine; the older `C:\MinGW` compiler is **32-bit** and must not be used
with 64-bit Python. Generated libraries and virtual environments are local
artifacts: rebuild them on another machine.

The machine has an NVIDIA RTX 4060 Laptop GPU, but no CUDA Toolkit compiler was
found during implementation. The supplied local binary therefore enables CPU
and OpenMP. CUDA source is included; it must be built and tested with the Toolkit.
The UI reports this as “GPU not available in this build”, never as measured CUDA
performance. See `VALIDATION.md` for what was actually tested.

## File-by-file tour / build order

1. **`src/common.h`** — shared hash, workload drift, equation, throttle rule,
   settings, statistics layout, and exported C declarations. Read this first.
2. **`src/state.h`** — one simulation's arrays and internal backend declarations.
3. **`src/cpu_sim.cpp`** — ordinary nested loops and a sequential statistics pass;
   this is the reference answer.
4. **`src/omp_sim.cpp`** — the same equation using `parallel for collapse(2)` and
   an OpenMP reduction. Comments identify private variables and barriers.
5. **`src/cuda_sim.cu`** — 16 × 16 diffusion kernels, optional shared-memory halo,
   two-pass block reductions, device allocation, selective edits, and event timing.
6. **`src/api.cpp`** — handle ownership, input checks, backend dispatch, timing,
   and exception-to-error conversion across the plain C ABI.
7. **`server/native.py`** — typed `ctypes` signatures and a small `Simulation`
   wrapper; explicitly closes native handles.
8. **`server/app.py`** — Flask routes, request validation, presets, and a background
   benchmark job. A lock protects the shared live simulation.
9. **`web/index.html`, `web/app.js`** — live heatmap, selections, editing, presets,
   hover tooltips, stats, and a rolling two-axis chart.
10. **`web/benchmark.html`, `web/benchmark.js`** — benchmark progress, bar/line
    charts, verified results, and CSV export. Exactly two UI pages.
11. **`web/style.css`** — responsive layout; no CSS framework.
12. **`CMakeLists.txt`** — shared-library build with required OpenMP and optional
    CUDA. `tests/test_simulation.py` checks the model and Flask contract.

## Architecture

```text
 Browser: HTML + CSS + JS + Canvas + Chart.js
   / Live Simulation          /benchmark-page Performance
               | JSON requests / responses
               v
 Flask server: validation, one live handle, benchmark worker
               | ctypes / extern "C" ABI
               v
         C++ shared library (thermal)
          /            |              \
 Sequential CPU     OpenMP CPU       CUDA GPU
 nested loops       shared RAM       global device RAM
                    loop workers     16x16 blocks
          \            |              /
           same hash, equation, and initial conditions
```

Flat index: `i = row * N + column`. Temperature, workload, and cooling use flat
`float` arrays. Temperature has a second buffer. C++ owns all native state;
Python owns the handle and calls `dc_destroy` when replacing it.

## Equations and deliberate simplifications

Every step, in this order:

```text
random_delta = hash(cell_index, step) % 5 - 2   // integer in [-2,+2]
workload = clamp(workload + random_delta, 0, 100)

effective_cooling = cooling + (25 - ambient)
neighbor_average = sum(existing N/S/W/E neighbors) / neighbor_count
T_new = T + alpha * (neighbor_average - T)
          + beta * workload - gamma * effective_cooling

alpha = 0.2; beta = 0.01; gamma = 0.01
effective_workload = T_new > 85 ? workload * 0.7 : workload
throughput = sum(effective_workload)
hotspot_count = count(T_new > adjustable_hotspot_threshold)
```

- Ambient defaults to 25 °C, so the thermal equation becomes exactly the basic
  diffusion + workload − cooling equation. Warmer ambient reduces cooling by
  one cooling unit per degree; negative effective cooling represents ambient
  heat input. This is a simple teaching approximation.
- Edges average only existing neighbors. A 1 × 1 test grid uses its own value
  as the neighbor average, so diffusion is zero.
- Initial temperature is 25 °C, workload is deterministic 45–55%, cooling is 50%.
- The random hash uses defined unsigned 32-bit overflow. Scheduling does not
  affect it. No shared `rand()` state and no per-backend random generators.
- Throttling changes **effective throughput**, not stored workload or heat
  generation. It always uses 85 °C. The adjustable hotspot threshold only changes
  classification and outlines. Raising it does not change the physics.
- “Shut down rack” sets workload to zero at that moment. The specified workload
  drift still applies on following steps; this is not a persistent power-off flag.
- There is no temperature clamp, ambient relaxation term, or airflow model.
  Strong unbalanced cooling can eventually produce unrealistic temperatures;
  long unbalanced heating can grow without bound. The color scale saturates at
  20–110 °C; the tooltip/stats still show actual values. Reset between demos.

## Parallel concepts for the viva

**Independence and double buffering.** Threads read the old temperature array
and write distinct indices of the next array. In-place updates would let some
cells see this step's neighbors and others see the previous step. Swap pointers
after the loop/kernel; do not copy the whole array to swap it.

**OpenMP.** `#pragma omp parallel for collapse(2) schedule(static)` distributes
the N × N iteration space across CPU workers sharing host RAM. Loop-local
variables are private. The implicit barrier completes all writes before swap.
`reduction(+:sum,throughput,hotspots)` and `reduction(max:maximum)` combine each
worker's partial statistics without racing on one global counter.

**CUDA hierarchy.** A block is 16 × 16 = 256 threads. A 2D grid of blocks covers
the rack grid. Bounds checks allow incomplete edge blocks. Adjacent x threads
touch adjacent array elements, improving coalescing.

**Memory and tiling.** Global device memory holds old/new temperatures, workload,
and cooling for the lifetime of a simulation. The optional tile caches 18 × 18
temperatures (16 × 16 interior + one-cell halo) in shared memory. Every thread
reaches `__syncthreads()` before edge threads return. Tiling is not guaranteed
to beat global memory: loading halos/barriers has a cost, and GPU caches help.

**Reduction.** A separate kernel reduces 256 cells at a time in shared memory.
A second kernel reduces the partial blocks to one result. It calculates maximum,
sum/average, hotspot count, and throughput, without global atomic contention.
Temperature arrays are floats; accumulated sums use doubles.

**Synchronization and transfers.** Default-stream launches execute in order.
`cudaDeviceSynchronize()` is called between steps. Frames copy all three fields
only when `/frame` is requested. `/step` returns just the tiny statistics result;
benchmark timing excludes that result transfer. Edits transfer only selected
indices/scalars and run a small GPU kernel. Every CUDA allocation has cleanup;
checked runtime/kernel errors become readable API errors.

**Timing.** CPU/OpenMP use `steady_clock`; CUDA compute time uses CUDA events
around diffusion + reduction. Live “ms / step” is native compute time (averaged
over the most recent batch). Benchmark bars use the same Python `perf_counter`
wall interval for every backend and include per-step synchronization overhead.
CUDA event time is also exported in CSV. Browser/network time is excluded.

## Build and run on Linux

Requirements: Python 3.10+, g++, OpenMP runtime, CMake 3.24+, optionally a compatible
NVIDIA driver + CUDA Toolkit with `nvcc` on PATH.

```bash
# Ubuntu/Debian prerequisites
sudo apt install build-essential cmake python3-venv
cd datacenter-thermal
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt

# CMake automatically enables CUDA if it finds nvcc; otherwise CPU + OpenMP.
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
OMP_NUM_THREADS=8 .venv/bin/python server/app.py
```

To explicitly build without CUDA, configure with `-DENABLE_CUDA=OFF`.
If multiple toolkits exist, set `-DCMAKE_CUDA_COMPILER=/path/to/cuda/bin/nvcc`.
If the toolkit default does not cover your GPU, set `-DCMAKE_CUDA_ARCHITECTURES`
to your GPU's compute capability (for example `89` for this RTX 4060).

Direct commands, as an alternative to CMake:

```bash
mkdir -p build
# CPU and OpenMP
g++ -O3 -std=c++14 -fPIC -shared -fopenmp -ffp-contract=off \
  src/api.cpp src/cpu_sim.cpp src/omp_sim.cpp -o build/libthermal.so

# All three backends, using nvcc and its supported g++ host compiler
nvcc -O3 -std=c++14 --fmad=false -DWITH_CUDA \
  -Xcompiler=-fPIC,-fopenmp,-ffp-contract=off -shared \
  src/api.cpp src/cpu_sim.cpp src/omp_sim.cpp src/cuda_sim.cu \
  -o build/libthermal.so
```

## Build and run on Windows

Use **64-bit Python and a 64-bit compiler**. Native Windows `nvcc` requires a
supported Visual Studio/MSVC toolchain; MinGW g++ is for the CPU/OpenMP build.
For nvcc + g++ together, use Linux/WSL2. See the official
[NVIDIA Windows installation guide](https://docs.nvidia.com/cuda/cuda-installation-guide-microsoft-windows/).

### CPU + OpenMP using MinGW-w64 (PowerShell)

Install a 64-bit MinGW-w64 toolchain and CMake. On this machine:

```powershell
cd C:\Users\Saarthak\Desktop\datacenter_final\datacenter-thermal
$env:PATH = 'C:\Program Files\CodeBlocks\MinGW\bin;' + $env:PATH
g++ -dumpmachine # must report x86_64, not mingw32
cmake -S . -B build -G 'MinGW Makefiles' -DENABLE_CUDA=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:OMP_NUM_THREADS = '8'
.\.venv\Scripts\python.exe server\app.py
```

Direct g++ alternative:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
g++ -O3 -std=c++14 -shared -fopenmp -ffp-contract=off src/api.cpp src/cpu_sim.cpp src/omp_sim.cpp -o build/thermal.dll
```

If creating the venv fails at `ensurepip`, use the base Python's pip:

```powershell
python -m venv --without-pip .venv
python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
```

### CUDA + CPU + OpenMP using Visual Studio

Install a CUDA-supported Visual Studio 2022 C++ toolset (17.8+ for modern OpenMP),
Windows SDK, CUDA Toolkit and CMake 3.30+. Use an **x64 Native Tools Command Prompt
for VS 2022**. Keep this build separate from the MinGW `build` directory:

```bat
cd C:\Users\Saarthak\Desktop\datacenter_final\datacenter-thermal
nvcc --version
cl
cmake -S . -B build-cuda -G "Visual Studio 17 2022" -A x64 -DENABLE_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89
cmake --build build-cuda --config Release -j 4
set THERMAL_LIBRARY=%CD%\build-cuda\Release\thermal.dll
set OMP_NUM_THREADS=8
set PATH=%VCToolsRedistDir%debug_nonredist\x64\Microsoft.VC143.OpenMP.LLVM;%PATH%
.venv\Scripts\python.exe server\app.py
```

`89` targets the RTX 4060; choose your own GPU architecture on another machine.
Check CMake's output for **CUDA backend enabled**, then `/info` for availability.
The build uses `/openmp:llvm` for `collapse(2)` and max reductions; legacy
`/openmp` alone is not sufficient. See Microsoft's
[loop-collapse explanation](https://devblogs.microsoft.com/cppblog/open-mp-improvements-in-visual-studio-cpp/).
If `libomp140.x86_64.dll` is not on PATH, locate it in your Visual Studio installation
and add its containing directory. Keep the runtime supplied by that toolchain.

## Using the two pages

**Live Simulation:** choose CPU/OpenMP/CUDA and grid size (both reset state), then
Start, Pause, Step, or Reset. Speed is **steps per requested frame**, not guaranteed
wall-clock FPS. Browser frames are requested serially, with at least 100 ms between
requests. Large JSON frames cost time independently of native compute speed.

- Click one rack; drag a rectangle; Shift-click to toggle an extra rack.
- Select all / Clear selection manage the selection. White outlines show it;
  yellow outlines mark hotspots. Hover for temperature, workload and cooling.
- Apply sets all three panel values on all selected racks. Quick actions change
  only their named field. Workload/cooling sliders use 0–100%.
- Normal load sets the entire grid to 25 °C / 50% / 50%. Hot aisle sets workload
  100% and cooling 5%. Cooling failure sets cooling 0%; boost sets 100%.
  Region presets use your selection, otherwise the central quarter.
- Random spikes choose a reproducible 2% sample of the whole grid, set 95 °C,
  workload 100%, cooling 10%, and select those racks.

**Performance:** run 100 steps (default) at 128, 256, 512, 1024 and 2048. The worker
warms up each backend for five steps, creates a fresh identical grid, applies a
90 °C stress region with workload 95% and cooling 10%, then starts timing.
Initialization, allocation, warm-up, JSON, charting and full frame copies are
excluded. Live mutations are blocked during benchmarking; the live state is kept.

Rows appear as each size finishes. The table and charts show measured wall ms/step,
and speedup = CPU ms ÷ parallel ms. CUDA is skipped if unavailable, never replaced
by CPU results. The check compares final maximum temperature with tolerance
0.001 °C and explicitly names which backends were verified. Full-grid agreement
is tested separately. Export the results with Download CSV.

Small grids may lose to scheduling/kernel-launch overhead. Large grids benefit
from parallelism until memory bandwidth limits scaling. Repeat benchmarks under
similar power/thermal conditions if you need stable numbers; this app does not
promise that every parallel backend is faster.

## API examples

All POST bodies are JSON. Indices are zero-based; rectangle ends are inclusive.
Errors return `{"error": "readable reason"}` with HTTP 400/409. The teaching
server uses one live simulation shared by all tabs, runs on localhost, and is
not intended as a public multi-user service.

| Endpoint | Body / response |
|---|---|
| `POST /init` | `{"size":64,"backend":"openmp"}`; optional ambient, threshold, tiled |
| `POST /step` | `{"n":5}`; optional settings; `n:0` updates settings only |
| `GET /frame` | Flat temperature/workload/cooling arrays, settings, and stats |
| `POST /modify` | `{"indices":[0,1,64,65],"values":{"workload":100,"cooling":5}}` |
| `POST /modify` | `{"rectangle":{"r0":10,"c0":10,"r1":20,"c1":20},"values":{"delta":10}}` |
| `POST /preset` | `{"name":"hot-aisle"}`; optional indices or rectangle |
| `POST /benchmark` | `{"steps":100,"tiled":false}`; starts a job (HTTP 202) |
| `GET /benchmark` | Job status, progress, rows, verification and hardware info |
| `GET /info` | GPU availability/name, OpenMP worker count, CUDA block size |

Native C ABI callers must pass a live handle and sufficiently sized output arrays,
and serialize calls using the same handle. Python handles these requirements.

## Tests and demo

```bash
# Linux, from the project root
OMP_NUM_THREADS=4 .venv/bin/python -m unittest discover -s tests -v
```

```powershell
# Windows, with the compiler/OpenMP runtime directory on PATH
$env:OMP_NUM_THREADS = '4'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

CUDA cases (including non-multiple-of-16 grids and tiled/global parity) run
automatically when a CUDA-enabled library and device are available. No GPU means
only the explicit-unavailable branch is tested; that is not CUDA validation.

See [VIVA.md](VIVA.md) for 10 questions and [DEMO.md](DEMO.md) for the two-minute
walkthrough. Chart.js 4.4.8 is bundled under its [MIT license](web/vendor/Chart.js-LICENSE.md).
