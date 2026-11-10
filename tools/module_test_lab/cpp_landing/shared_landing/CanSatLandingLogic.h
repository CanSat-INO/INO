#pragma once
/*
 * CanSatLandingLogic.h
 * Portable landing judgment logic; does not use Arduino.h or any ESP32 API.
 * This demonstration is NOT the team's actual flight algorithm.
 * Keep this header identical in the Arduino sketch and host test.
 */
#include <math.h>

struct LandingLogicConfig {
    double impact_threshold_mps2;
    double detection_delay_ms;

    LandingLogicConfig(double impact_threshold = 20.0, double detection_delay = 3000.0)
        : impact_threshold_mps2(impact_threshold), detection_delay_ms(detection_delay) {}
};

class CanSatLandingLogic {
public:
    explicit CanSatLandingLogic(LandingLogicConfig cfg = LandingLogicConfig())
        : config_(cfg) { reset(); }

    void reset() {
        saw_impact_ = false;
        landed_ = false;
        impact_time_ms_ = 0.0;
    }

    // The IMU value is an example's Z-axis sample, NOT attitude-independent acceleration.
    // pressure_pa is reserved for a future team-specific algorithm and not yet used.
    // Input times must be non-negative and monotonic (consistent with Module Test Lab CSV).
    bool update(double time_ms, double imu_z_mps2, double pressure_pa) {
        (void)pressure_pa;
        if (landed_) return true;
        if (!isfinite(time_ms) || !isfinite(imu_z_mps2) || time_ms < 0.0) return false;
        if (!isfinite(config_.impact_threshold_mps2) || config_.impact_threshold_mps2 <= 0.0 ||
            !isfinite(config_.detection_delay_ms) || config_.detection_delay_ms < 0.0) return false;
        if (!saw_impact_ && fabs(imu_z_mps2) >= config_.impact_threshold_mps2) {
            saw_impact_ = true;
            impact_time_ms_ = time_ms;
        }
        if (saw_impact_ && time_ms >= impact_time_ms_ &&
            (time_ms - impact_time_ms_) >= config_.detection_delay_ms) {
            landed_ = true;
        }
        return landed_;
    }

private:
    LandingLogicConfig config_;
    bool saw_impact_;
    bool landed_;
    double impact_time_ms_;
};
