#pragma once
// ホストPC用の最小インターフェースです。
// Arduinoから移植する場合、センサー読み取りではなく判定部分を実装してください。
// time_ms は計測開始後のミリ秒、imu_z_mps2 はZ加速度、pressure_pa は気圧。
// 気圧がCSVで空欄のとき pressure_pa=-1.0 が渡されます。
// すべての入力は時刻昇順で渡されます。
// 戻り値: 0=未検知, 1=着地検知済み (ラッチする実装を推奨)。
extern "C" void landing_reset();
extern "C" int landing_step(double time_ms, double imu_z_mps2, double pressure_pa);
