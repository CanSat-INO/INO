#pragma once
#include <stdint.h>

// 機種非依存の仮形式。座標系・精度・時刻の基準は今後チームで決定する。
struct SensorSample {
    uint32_t elapsed_ms;
    float acceleration_mps2[3];
    float pressure_pa;
    bool imu_valid;
    bool pressure_valid;
};
