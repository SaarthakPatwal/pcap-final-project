#pragma once
#include <cstdint>

// The SAME small functions are compiled for CPU and GPU. No random-number state
// is shared between threads, so scheduling cannot change the answer.
#ifdef __CUDACC__
#define HD __host__ __device__
#else
#define HD
#endif

struct Settings {
    float alpha = 0.2f, beta = 0.01f, gamma = 0.01f;
    float ambient = 25.0f, threshold = 85.0f;
    int tiled = 0;
};

HD inline uint32_t cell_hash(uint32_t index, uint32_t step) {
    uint32_t x = index ^ (step * 747796405u + 2891336453u);
    x ^= x >> 16; x *= 2246822519u;
    x ^= x >> 13; x *= 3266489917u;
    return x ^ (x >> 16);
}
HD inline float drift(float workload, int index, uint32_t step) {
    float w = workload + float(int(cell_hash(uint32_t(index), step) % 5u) - 2);
    return w < 0 ? 0 : (w > 100 ? 100 : w);
}
HD inline float next_temperature(float t, float sum, int neighbors,
                                 float w, float cooling, Settings s) {
    float average = neighbors ? sum / float(neighbors) : t;
    // Ambient 25 C reproduces the requested equation exactly. Warmer intake
    // reduces effective cooling; negative effective cooling means ambient heat.
    float effective_cooling = cooling + (25.0f - s.ambient);
    return t + s.alpha * (average - t) + s.beta * w - s.gamma * effective_cooling;
}
HD inline float effective_workload(float temperature, float workload) {
    // Throttling always starts at 85 C. The display hotspot threshold is separate.
    return temperature > 85.0f ? workload * 0.7f : workload;
}

// All-double output avoids platform-dependent packing in Python ctypes.
struct Stats { double maximum, average, hotspots, throughput, step, milliseconds; };

#ifdef _WIN32
#define EXPORT extern "C" __declspec(dllexport)
#else
#define EXPORT extern "C" __attribute__((visibility("default")))
#endif
EXPORT void* dc_create(int size, int backend); // 0=CPU, 1=OpenMP, 2=CUDA
EXPORT void dc_destroy(void* handle);
EXPORT int dc_step(void* handle, int count);
EXPORT int dc_configure(void* handle, float ambient, float threshold, int tiled);
EXPORT int dc_modify(void* handle, const int* indices, int count, int mask,
                     float temperature, float workload, float cooling, float delta);
EXPORT int dc_frame(void* handle, float* temperatures, float* workloads,
                    float* cooling, Stats* stats);
EXPORT int dc_stats(void* handle, Stats* stats);
EXPORT const char* dc_error();
EXPORT int dc_omp_threads();
EXPORT int dc_cuda_available();
EXPORT const char* dc_gpu_name();
