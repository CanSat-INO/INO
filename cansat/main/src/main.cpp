#include <Arduino.h>
#include "Telemetry.h"

void setup() { Serial.begin(115200); }

void loop() {
    static uint32_t last_ms = 0;
    const uint32_t now_ms = millis();
    if (now_ms - last_ms < 1000) return;
    last_ms = now_ms;
    const SensorSample sample = makeExampleSample(now_ms);
    Serial.printf("EXAMPLE ms=%lu imu_valid=%d pressure_valid=%d\\n",
                  static_cast<unsigned long>(sample.elapsed_ms),
                  sample.imu_valid, sample.pressure_valid);
}
