#pragma once
#include "common.h"
#include <vector>

struct State {
    int n, backend;
    uint32_t step = 0;
    Settings settings;
    Stats stats{};
    std::vector<float> temperature, next, workload, cooling;
    void* gpu = nullptr;
    State(int size, int mode) : n(size), backend(mode),
        temperature(size * size, 25), next(size * size, 25),
        workload(size * size), cooling(size * size, 50) {
        for (int i = 0; i < size * size; ++i)
            workload[i] = 45.0f + float(cell_hash(i, 0) % 11u);
    }
};
void cpu_step(State& s);
void cpu_stats(State& s);
void omp_step(State& s);
void omp_stats(State& s);

#ifdef WITH_CUDA
void gpu_create(State& s);
void gpu_destroy(State& s);
void gpu_step(State& s);
void gpu_reduce(State& s);
void gpu_stats(State& s);
void gpu_frame(State& s);
void gpu_modify(State& s, const int* indices, int count, int mask,
                float t, float w, float c, float delta);
bool gpu_available();
const char* gpu_name();
#endif
