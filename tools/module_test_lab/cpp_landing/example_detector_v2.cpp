// v6学習用の比較例。実機への搭載は禁止ではないが、実機検証済みではありません。
// v5の合成CSVで改善と退行を考えるためのサンプルです。
// 重要: pressure_pa はv5生成データの「着地後の平坦化」に強く依存しています。
// 実機の気圧が着地後に同様に平坦化する保証はありません。
#include "landing_api.h"
#include <cmath>
namespace {
    bool saw_impact = false;
    bool landed = false;
    double stable_since_ms = -1.0;
    double previous_pressure = -1.0;
}
extern "C" void landing_reset() {
    saw_impact = false;
    landed = false;
    stable_since_ms = -1.0;
    previous_pressure = -1.0;
}
extern "C" int landing_step(double time_ms, double imu_z_mps2, double pressure_pa) {
    if (landed) return 1;
    if (std::fabs(imu_z_mps2) >= 13.5) saw_impact = true;
    // ミッション用ではなく固定周期・仮想気圧に合わせた単純な比較例。
    const bool stable = (previous_pressure > 0.0 && pressure_pa > 0.0 &&
                         std::fabs(pressure_pa - previous_pressure) <= 0.02);
    previous_pressure = pressure_pa;
    if (!saw_impact) return 0;
    if (!stable) stable_since_ms = -1.0;
    else if (stable_since_ms < 0.0) stable_since_ms = time_ms;
    if (stable_since_ms >= 0.0 && time_ms - stable_since_ms >= 300.0) landed = true;
    return landed ? 1 : 0;
}
