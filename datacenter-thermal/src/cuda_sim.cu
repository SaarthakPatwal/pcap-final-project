#include "state.h"
#include <cuda_runtime.h>
#include <stdexcept>
#include <string>
#include <utility>
#include <math_constants.h>

#define CUDA_CHECK(call) do { cudaError_t error = (call); \
    if (error != cudaSuccess) throw std::runtime_error( \
        std::string(#call) + ": " + cudaGetErrorString(error)); } while (0)

namespace {
constexpr int SIDE = 16, THREADS = SIDE * SIDE;
struct Partial { double sum, throughput; float maximum; int hotspots; };
struct Device {
    float *temperature = nullptr, *next = nullptr, *workload = nullptr, *cooling = nullptr;
    Partial *partials = nullptr, *result = nullptr;
    cudaEvent_t start = nullptr, stop = nullptr;
    int blocks = 0;
};

__global__ void diffusion(const float* old, float* next, float* work,
                          const float* cool, int n, uint32_t step, Settings s) {
    // Two-dimensional launch: one GPU thread owns one rack.
    int col = blockIdx.x * SIDE + threadIdx.x;
    int row = blockIdx.y * SIDE + threadIdx.y;
    if (row >= n || col >= n) return;
    int i = row * n + col, count = 0;
    float sum = 0;
    if (row > 0)     { sum += old[i - n]; ++count; }
    if (row < n - 1) { sum += old[i + n]; ++count; }
    if (col > 0)     { sum += old[i - 1]; ++count; }
    if (col < n - 1) { sum += old[i + 1]; ++count; }
    work[i] = drift(work[i], i, step);
    next[i] = next_temperature(old[i], sum, count, work[i], cool[i], s);
}

__global__ void diffusion_tiled(const float* old, float* next, float* work,
                                const float* cool, int n, uint32_t step, Settings s) {
    // The 16x16 interior plus a one-cell halo fits in 18x18 shared floats.
    __shared__ float tile[SIDE + 2][SIDE + 2];
    int lane = threadIdx.y * SIDE + threadIdx.x;
    // Cooperatively load the whole tile, including the halo. Out-of-grid values
    // are initialized but never included in the neighbor average below.
    for (int k = lane; k < (SIDE + 2) * (SIDE + 2); k += THREADS) {
        int y = k / (SIDE + 2), x = k % (SIDE + 2);
        int r = int(blockIdx.y) * SIDE + y - 1;
        int c = int(blockIdx.x) * SIDE + x - 1;
        tile[y][x] = (r >= 0 && r < n && c >= 0 && c < n) ? old[r * n + c] : 0;
    }
    __syncthreads(); // ALL threads must reach this, even in a partial edge block.
    int row = blockIdx.y * SIDE + threadIdx.y, col = blockIdx.x * SIDE + threadIdx.x;
    if (row >= n || col >= n) return;
    int y = threadIdx.y + 1, x = threadIdx.x + 1, i = row * n + col, count = 0;
    float sum = 0;
    if (row > 0)     { sum += tile[y - 1][x]; ++count; }
    if (row < n - 1) { sum += tile[y + 1][x]; ++count; }
    if (col > 0)     { sum += tile[y][x - 1]; ++count; }
    if (col < n - 1) { sum += tile[y][x + 1]; ++count; }
    work[i] = drift(work[i], i, step);
    next[i] = next_temperature(tile[y][x], sum, count, work[i], cool[i], s);
}

__device__ Partial empty_partial() { return {0, 0, -CUDART_INF_F, 0}; }
__device__ Partial combine(Partial a, Partial b) {
    return {a.sum + b.sum, a.throughput + b.throughput,
            fmaxf(a.maximum, b.maximum), a.hotspots + b.hotspots};
}
__device__ void reduce_block(Partial value, Partial* output) {
    __shared__ Partial scratch[THREADS];
    int lane = threadIdx.x;
    scratch[lane] = value;
    __syncthreads();
    // Tree reduction: 256 values -> 128 -> 64 -> ... -> 1.
    for (int stride = THREADS / 2; stride > 0; stride /= 2) {
        if (lane < stride) scratch[lane] = combine(scratch[lane], scratch[lane + stride]);
        __syncthreads();
    }
    if (lane == 0) *output = scratch[0];
}
__global__ void reduce_cells(const float* t, const float* w, int size,
                             float threshold, Partial* partials) {
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    Partial p = empty_partial();
    if (i < size) p = {double(t[i]), double(effective_workload(t[i], w[i])),
                      t[i], int(t[i] > threshold)};
    reduce_block(p, partials + blockIdx.x);
}
__global__ void reduce_partials(const Partial* partials, int count, Partial* result) {
    Partial p = empty_partial();
    for (int i = threadIdx.x; i < count; i += THREADS) p = combine(p, partials[i]);
    // Second pass avoids contended atomics and works without double atomicAdd.
    reduce_block(p, result);
}
__global__ void modify_cells(float* t, float* w, float* c, const int* indices,
                             int count, int mask, float tv, float wv, float cv, float delta) {
    int j = blockIdx.x * blockDim.x + threadIdx.x;
    if (j >= count) return;
    int i = indices[j]; // API guarantees unique, validated indices.
    if (mask & 1) t[i] = tv;
    if (mask & 2) w[i] = wv;
    if (mask & 4) c[i] = cv;
    if (mask & 8) t[i] += delta;
}
} // namespace

bool gpu_available() {
    int count = 0;
    return cudaGetDeviceCount(&count) == cudaSuccess && count > 0;
}
const char* gpu_name() {
    static thread_local std::string name;
    cudaDeviceProp properties{};
    if (!gpu_available() || cudaGetDeviceProperties(&properties, 0) != cudaSuccess)
        return "GPU not available (check NVIDIA device and driver)";
    name = properties.name;
    return name.c_str();
}
void gpu_create(State& s) {
    Device* d = new Device;
    s.gpu = d;
    size_t bytes = size_t(s.n) * s.n * sizeof(float);
    d->blocks = (s.n * s.n + THREADS - 1) / THREADS;
    try {
        CUDA_CHECK(cudaMalloc(&d->temperature, bytes));
        CUDA_CHECK(cudaMalloc(&d->next, bytes));
        CUDA_CHECK(cudaMalloc(&d->workload, bytes));
        CUDA_CHECK(cudaMalloc(&d->cooling, bytes));
        CUDA_CHECK(cudaMalloc(&d->partials, d->blocks * sizeof(Partial)));
        CUDA_CHECK(cudaMalloc(&d->result, sizeof(Partial)));
        CUDA_CHECK(cudaEventCreate(&d->start));
        CUDA_CHECK(cudaEventCreate(&d->stop));
        CUDA_CHECK(cudaMemcpy(d->temperature, s.temperature.data(), bytes, cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d->workload, s.workload.data(), bytes, cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(d->cooling, s.cooling.data(), bytes, cudaMemcpyHostToDevice));
        gpu_reduce(s);
    } catch (...) { gpu_destroy(s); throw; }
}
void gpu_destroy(State& s) {
    Device* d = static_cast<Device*>(s.gpu);
    if (!d) return;
    // Cleanup is best-effort and must not throw across a C destructor boundary.
    cudaFree(d->temperature); cudaFree(d->next);
    cudaFree(d->workload); cudaFree(d->cooling);
    cudaFree(d->partials); cudaFree(d->result);
    if (d->start) cudaEventDestroy(d->start);
    if (d->stop) cudaEventDestroy(d->stop);
    delete d;
    s.gpu = nullptr;
}
void gpu_reduce(State& s) {
    Device& d = *static_cast<Device*>(s.gpu);
    reduce_cells<<<d.blocks, THREADS>>>(d.temperature, d.workload, s.n * s.n,
                                       s.settings.threshold, d.partials);
    CUDA_CHECK(cudaGetLastError());
    reduce_partials<<<1, THREADS>>>(d.partials, d.blocks, d.result);
    CUDA_CHECK(cudaGetLastError());
}
void gpu_step(State& s) {
    Device& d = *static_cast<Device*>(s.gpu);
    dim3 block(SIDE, SIDE), grid((s.n + SIDE - 1) / SIDE, (s.n + SIDE - 1) / SIDE);
    CUDA_CHECK(cudaEventRecord(d.start));
    if (s.settings.tiled)
        diffusion_tiled<<<grid, block>>>(d.temperature, d.next, d.workload, d.cooling,
                                        s.n, s.step, s.settings);
    else
        diffusion<<<grid, block>>>(d.temperature, d.next, d.workload, d.cooling,
                                   s.n, s.step, s.settings);
    CUDA_CHECK(cudaGetLastError());
    std::swap(d.temperature, d.next);
    ++s.step;
    gpu_reduce(s);
    CUDA_CHECK(cudaEventRecord(d.stop));
    CUDA_CHECK(cudaDeviceSynchronize()); // Kernel completion before next step.
    float elapsed = 0;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed, d.start, d.stop));
    s.stats.milliseconds = elapsed;
    // No grid transfer here: all four arrays stay allocated on the device.
}
void gpu_stats(State& s) {
    Device& d = *static_cast<Device*>(s.gpu);
    Partial result;
    CUDA_CHECK(cudaMemcpy(&result, d.result, sizeof(result), cudaMemcpyDeviceToHost));
    s.stats = {result.maximum, result.sum / (s.n * s.n), double(result.hotspots),
               result.throughput, double(s.step), s.stats.milliseconds};
}
void gpu_frame(State& s) {
    Device& d = *static_cast<Device*>(s.gpu);
    size_t bytes = size_t(s.n) * s.n * sizeof(float);
    CUDA_CHECK(cudaMemcpy(s.temperature.data(), d.temperature, bytes, cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(s.workload.data(), d.workload, bytes, cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaMemcpy(s.cooling.data(), d.cooling, bytes, cudaMemcpyDeviceToHost));
    gpu_stats(s);
}
void gpu_modify(State& s, const int* indices, int count, int mask,
                float t, float w, float c, float delta) {
    if (!count) return;
    Device& d = *static_cast<Device*>(s.gpu);
    int* device_indices = nullptr;
    CUDA_CHECK(cudaMalloc(&device_indices, size_t(count) * sizeof(int)));
    try {
        CUDA_CHECK(cudaMemcpy(device_indices, indices, size_t(count) * sizeof(int), cudaMemcpyHostToDevice));
        modify_cells<<<(count + THREADS - 1) / THREADS, THREADS>>>(
            d.temperature, d.workload, d.cooling, device_indices, count, mask, t, w, c, delta);
        CUDA_CHECK(cudaGetLastError());
        gpu_reduce(s);
        CUDA_CHECK(cudaDeviceSynchronize());
    } catch (...) { cudaFree(device_indices); throw; }
    CUDA_CHECK(cudaFree(device_indices));
}
