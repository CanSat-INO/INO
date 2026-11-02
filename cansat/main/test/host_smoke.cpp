#include "Telemetry.h"
#include <cassert>
int main() {
    const auto sample = makeExampleSample(1234);
    assert(sample.elapsed_ms == 1234);
    assert(!sample.imu_valid && !sample.pressure_valid);
}
