# Viva cheat sheet: 10 likely questions

1. **Why double buffering?** Every rack must use its neighbors from the same old
   time step. Separate old/new arrays avoid races and order-dependent physics.
   Swap the arrays after all threads finish; swapping pointers is cheap.

2. **Why one CUDA thread per cell?** Each cell performs the same small calculation
   independently. Mapping x/y to column/row makes indexing easy and gives many
   parallel jobs. A bounds check handles partial edge blocks.

3. **Why 16 × 16 blocks?** That is 256 threads, a multiple of the 32-thread warp,
   and a convenient square shape for neighbor access. It is a reasonable teaching
   choice, not a claim that it is optimal on every GPU.

4. **What causes speedup, and why can OpenMP/CUDA be slower?** Many cells run
   concurrently. Thread startup, barriers and kernel launches cost time, so small
   grids may not provide enough work. Large grids can become bandwidth-limited.

5. **What does OpenMP `collapse(2)` mean?** It combines the row and column loops
   into one N × N iteration space. OpenMP divides that space among CPU workers.
   Loop-local sums and counts are private; arrays are shared.

6. **What is a reduction?** It combines many values into one, such as maximum,
   sum or count. OpenMP manages per-thread partials with reduction clauses. CUDA
   combines values in shared-memory trees, then reduces the partial blocks.

7. **How does OpenMP differ from CUDA?** OpenMP uses CPU threads sharing host RAM
   and is easy to add to loops. CUDA launches GPU threads in blocks and explicitly
   manages device buffers, kernels, transfers and synchronization.

8. **What is shared-memory tiling?** A block loads its temperatures and one-cell
   halo into fast shared memory, reuses those neighbor values, then synchronizes.
   All threads must reach the barrier before out-of-range threads return.
   Extra loading/barriers mean tiling may not always win.

9. **How do you ensure fair and correct comparisons?** Identical initial data,
   step counts, settings, and index/step hashes; double buffering; no fused
   multiply-add differences; warm-up outside timing. Compare final maximum within
   0.001 °C, and use tests to compare every grid cell. Missing CUDA is skipped.

10. **How do edits and throttling work?** The UI sends a list or rectangle; CPU
    loops or a GPU edit kernel change every selected cell. Duplicate indices are
    removed. Above 85 °C, effective workload is 70% of the requested workload,
    reducing throughput. Throttling does not reduce the heat-generation term in
    this intentionally simple model. The hotspot display threshold is separate.

Useful one-line formula: `speedup = CPU time / parallel time`. A speedup below 1
means the parallel run was slower. Report measured results, not assumed ones.
