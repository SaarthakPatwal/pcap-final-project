#include "state.h"
#include <algorithm>
#include <limits>

void cpu_step(State& s) {
    const int n = s.n;
    for (int row = 0; row < n; ++row) {
        for (int col = 0; col < n; ++col) {
            int i = row * n + col, count = 0;
            float sum = 0;
            // Boundary cells average ONLY existing neighbors (no wraparound).
            if (row > 0)     { sum += s.temperature[i - n]; ++count; }
            if (row < n - 1) { sum += s.temperature[i + n]; ++count; }
            if (col > 0)     { sum += s.temperature[i - 1]; ++count; }
            if (col < n - 1) { sum += s.temperature[i + 1]; ++count; }
            s.workload[i] = drift(s.workload[i], i, s.step);
            s.next[i] = next_temperature(s.temperature[i], sum, count,
                                         s.workload[i], s.cooling[i], s.settings);
        }
    }
    // Double buffering: every cell read the old grid, never a half-updated one.
    s.temperature.swap(s.next);
    ++s.step;
    cpu_stats(s);
}

void cpu_stats(State& s) {
    double sum = 0, throughput = 0;
    float maximum = -std::numeric_limits<float>::infinity();
    int hotspots = 0;
    for (int i = 0; i < s.n * s.n; ++i) {
        float t = s.temperature[i];
        maximum = std::max(maximum, t);
        sum += t;
        hotspots += t > s.settings.threshold;
        throughput += effective_workload(t, s.workload[i]);
    }
    s.stats = {maximum, sum / (s.n * s.n), double(hotspots), throughput,
               double(s.step), s.stats.milliseconds};
}
