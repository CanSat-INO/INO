// Host-side adapter: use precisely the same CanSatLandingLogic class as Arduino.
// The existing Module Test Lab compiles this file alongside cpp_landing/runner.cpp.
#include "../landing_api.h"
#include "CanSatLandingLogic.h"

namespace {
CanSatLandingLogic detector;
}

extern "C" void landing_reset() { detector.reset(); }

extern "C" int landing_step(double time_ms, double imu_z_mps2, double pressure_pa) {
    return detector.update(time_ms, imu_z_mps2, pressure_pa) ? 1 : 0;
}
