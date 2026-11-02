#pragma once
#include "SensorSample.h"

// 仮データを渡す例。着地判定や機器制御は含まない。
SensorSample makeExampleSample(uint32_t elapsed_ms);
