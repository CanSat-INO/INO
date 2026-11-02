#include "Telemetry.h"

SensorSample makeExampleSample(uint32_t elapsed_ms) {
    return {elapsed_ms, {0.0f, 0.0f, 0.0f}, 0.0f, false, false};
}
