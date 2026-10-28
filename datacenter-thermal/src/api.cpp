#include "state.h"
#include <omp.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
thread_local std::string last_error;
State& state(void* handle) {
    if (!handle) throw std::runtime_error("Simulation is not initialized");
    return *static_cast<State*>(handle);
}
void refresh(State& s) {
#ifdef WITH_CUDA
    if (s.backend == 2) { gpu_reduce(s); return; }
#endif
    if (s.backend == 1) omp_stats(s); else cpu_stats(s);
}
// Exceptions must never cross the plain C ABI into Python.
template<class Action> int guarded(Action action) {
    try { last_error.clear(); action(); return 0; }
    catch (const std::exception& e) { last_error = e.what(); return -1; }
    catch (...) { last_error = "Unknown native error"; return -1; }
}
}

void* dc_create(int n, int backend) {
    void* output = nullptr;
    guarded([&] {
        if (n < 1 || n > 2048 || backend < 0 || backend > 2)
            throw std::runtime_error("Invalid grid size or backend");
        if (backend == 2 && !dc_cuda_available()) throw std::runtime_error(dc_gpu_name());
        std::unique_ptr<State> s(new State(n, backend));
#ifdef WITH_CUDA
        if (backend == 2) gpu_create(*s); else
#endif
        refresh(*s);
        output = s.release();
    });
    return output;
}
void dc_destroy(void* handle) {
    if (!handle) return;
    State* s = static_cast<State*>(handle);
#ifdef WITH_CUDA
    if (s->gpu) gpu_destroy(*s);
#endif
    delete s;
}
int dc_step(void* handle, int count) {
    return guarded([&] {
        State& s = state(handle);
        if (count < 1 || count > 10000) throw std::runtime_error("Steps must be 1..10000");
        double total_ms = 0;
        for (int i = 0; i < count; ++i) {
#ifdef WITH_CUDA
            if (s.backend == 2) { gpu_step(s); total_ms += s.stats.milliseconds; continue; }
#endif
            auto start = std::chrono::steady_clock::now();
            if (s.backend == 1) omp_step(s); else cpu_step(s);
            total_ms += std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - start).count();
        }
        s.stats.milliseconds = total_ms / count;
    });
}
int dc_configure(void* handle, float ambient, float threshold, int tiled) {
    return guarded([&] {
        State& s = state(handle);
        if (!std::isfinite(ambient) || ambient < 10 || ambient > 45 ||
            !std::isfinite(threshold) || threshold < 30 || threshold > 120 ||
            (tiled != 0 && tiled != 1)) throw std::runtime_error("Invalid environment settings");
        s.settings.ambient = ambient; s.settings.threshold = threshold; s.settings.tiled = tiled;
        refresh(s);
    });
}
int dc_modify(void* handle, const int* indices, int count, int mask,
              float t, float w, float c, float delta) {
    return guarded([&] {
        State& s = state(handle);
        if (count < 0 || count > s.n * s.n || (count && !indices) || mask < 1 || mask > 15)
            throw std::runtime_error("Invalid selection or modification mask");
        if (((mask & 1) && (!std::isfinite(t) || t < -100 || t > 500)) ||
            ((mask & 2) && (!std::isfinite(w) || w < 0 || w > 100)) ||
            ((mask & 4) && (!std::isfinite(c) || c < 0 || c > 100)) ||
            ((mask & 8) && (!std::isfinite(delta) || std::abs(delta) > 100)))
            throw std::runtime_error("Invalid cell values");
        // Sort+unique prevents two GPU threads racing on the same selected rack.
        std::vector<int> unique;
        if (count) unique.assign(indices, indices + count);
        std::sort(unique.begin(), unique.end());
        unique.erase(std::unique(unique.begin(), unique.end()), unique.end());
        for (int i : unique) if (i < 0 || i >= s.n * s.n)
            throw std::runtime_error("Cell index is outside the grid");
#ifdef WITH_CUDA
        if (s.backend == 2) {
            gpu_modify(s, unique.data(), int(unique.size()), mask, t, w, c, delta);
            return;
        }
#endif
        for (int i : unique) {
            if (mask & 1) s.temperature[i] = t;
            if (mask & 2) s.workload[i] = w;
            if (mask & 4) s.cooling[i] = c;
            if (mask & 8) s.temperature[i] += delta;
        }
        refresh(s);
    });
}
int dc_stats(void* handle, Stats* output) {
    return guarded([&] {
        State& s = state(handle);
        if (!output) throw std::runtime_error("Missing stats output");
#ifdef WITH_CUDA
        if (s.backend == 2) gpu_stats(s); // Only a tiny reduction result is copied.
#endif
        *output = s.stats;
    });
}
int dc_frame(void* handle, float* t, float* w, float* c, Stats* output) {
    return guarded([&] {
        State& s = state(handle);
        if (!t || !w || !c || !output) throw std::runtime_error("Missing frame outputs");
#ifdef WITH_CUDA
        if (s.backend == 2) gpu_frame(s); // This is the ONLY full device-to-host copy.
#endif
        std::copy(s.temperature.begin(), s.temperature.end(), t);
        std::copy(s.workload.begin(), s.workload.end(), w);
        std::copy(s.cooling.begin(), s.cooling.end(), c);
        *output = s.stats;
    });
}
const char* dc_error() { return last_error.c_str(); }
int dc_omp_threads() {
    int count = 1;
    #pragma omp parallel
    {
        #pragma omp single
        count = omp_get_num_threads();
    }
    return count;
}
int dc_cuda_available() {
#ifdef WITH_CUDA
    return gpu_available() ? 1 : 0;
#else
    return 0;
#endif
}
const char* dc_gpu_name() {
#ifdef WITH_CUDA
    return gpu_name();
#else
    return "GPU not available in this build (rebuild with the CUDA Toolkit)";
#endif
}
