// v7 synthetic-data STUDY DEMO. Does not establish real-world safety or performance.
// Requires landing_configure() before landing_reset() and landing_step().
// The pressure plateau in v5 scenarios is not guaranteed by real sensors.
#include "landing_api.h"
#include <cmath>
namespace {
    double impact_threshold = 14.0;
    double hold_duration_ms = 300.0;
    bool saw_impact = false;
    bool landed = false;
    double stable_since_ms = -1.0;
    double last_pressure = -1.0;
}
extern "C" void landing_configure(double threshold_mps2, double hold_ms) {
    impact_threshold = threshold_mps2;
    hold_duration_ms = hold_ms;
}
extern "C" void landing_reset() {
    saw_impact = false;
    landed = false;
    stable_since_ms = -1.0;
    last_pressure = -1.0;
}
extern "C" int landing_step(double time_ms,double imu_z_mps2,double pressure_pa) {
    if (landed) return 1;
    if (std::fabs(imu_z_mps2) >= impact_threshold) saw_impact = true;
    const bool stable = last_pressure > 0.0 && pressure_pa > 0.0 &&
                        std::fabs(pressure_pa-last_pressure) <= 0.02;
    last_pressure = pressure_pa;
    if (!saw_impact) return 0;
    if (!stable) stable_since_ms = -1.0;
    else if (stable_since_ms < 0.0) stable_since_ms = time_ms;
    if (stable_since_ms >= 0.0 && time_ms-stable_since_ms >= hold_duration_ms)
        landed = true;
    return landed ? 1 : 0;
}
