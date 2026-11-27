#include "sim_port.hpp"
// Host connection example only. Replace this adapter with calls into your real
// portable decision logic; no mission behavior is invented here.
int main() {
    cansat_sim::Sensors sensors;
    cansat_sim::Actuators outputs;
    while (cansat_sim::wait(100, outputs, sensors)) {
        outputs.left = outputs.right = 0; // Default: stop.
    }
}
