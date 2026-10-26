// 学習用の例示アルゴリズムです。ESP32-S3上での実際の着地検知コードではありません。
#include "landing_api.h"
#include <cmath>
namespace {
    bool saw_impact = false;
    bool landed = false;
    double impact_ms = 0.0;
}
extern "C" void landing_reset() {
    saw_impact = false;
    landed = false;
    impact_ms = 0.0;
}
extern "C" int landing_step(double time_ms, double imu_z_mps2, double pressure_pa) {
    (void)pressure_pa;
    if (landed) return 1;
    if (!saw_impact && std::fabs(imu_z_mps2) >= 20.0) {
        saw_impact = true;
        impact_ms = time_ms;
    }
    if (saw_impact && time_ms - impact_ms >= 3000.0) landed = true;
    return landed ? 1 : 0;
}
