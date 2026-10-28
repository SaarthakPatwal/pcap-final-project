# Two-minute demo script

Before presenting: start the server, open the live page, choose 64 × 64, select
CPU or OpenMP (CUDA only when available), and Reset. Keep the hotspot threshold
at 85 °C and ambient at 25 °C. Rehearse once because browser frame speed varies.

**0:00–0:20 — Introduce and select.**
“Each square is one rack. Its temperature depends on its four neighbors,
workload and cooling.” Drag a roughly 12 × 12 central region. Shift-click a rack
to add/remove it. Point to the selection count and white outlines.

**0:20–0:35 — Set up a visible fault.**
Set Temperature to **80 °C**, Workload to **100%**, Cooling to **5%**, then Apply.
Click **Max workload** to demonstrate a single-field batch action. Explain that
starting near 85 °C compresses the demo; the Hot aisle failure preset otherwise
heats from the normal 25 °C baseline and takes more steps.

**0:35–0:55 — Heat spreading and throttling.**
Set Steps/frame to **1**, click Start, and watch the colored boundary spread.
Pause when the hottest racks reach about **88–92 °C** (roughly 10–20 steps).
Point to yellow hotspot outlines. “Above 85 °C each hot rack contributes 30%
less effective workload. The total throughput chart includes the other racks
and their random drift, so it need not fall by exactly 30%.”

**0:55–1:20 — Recover with cooling.**
Click **Cooling boost** while keeping the same selection, set Steps/frame to
**5**, and Start. Leave the temperature and workload alone. Pause once hotspots
reach zero. “Maximum cooling, workload drift and outward heat diffusion let
this region recover.” In the tested 12 × 12 central region, 12 heating steps
created 96 hotspots; 80 subsequent steps with cooling 100% cleared all of them.
Larger regions or a longer heating phase take longer to recover.

**1:20–1:35 — Explain the implementation.**
“The reference uses CPU loops. OpenMP distributes the same loop across CPU
workers. CUDA uses one thread per rack in 16 × 16 blocks. All use double
buffering and the same deterministic workload changes.” Briefly show the CUDA
tiling checkbox if enabled, or the explicit unavailable-build message.

**1:35–2:00 — Compare performance.**
Open Performance and Run Benchmark (100 steps). Explain wall ms/step and CPU
speedup baseline 1×. Rows appear as sizes finish; the full run may exceed the
remaining time on slower hardware. Point to verification: same final maximum
within 0.001 °C, with CUDA explicitly skipped if unavailable. Export CSV once
complete. Do not claim GPU speedup from a CPU-only build.

For a shorter rehearsal, use 10 benchmark steps. Use the default 100 for the
reported measurements. Reset before repeating the live demonstration.
