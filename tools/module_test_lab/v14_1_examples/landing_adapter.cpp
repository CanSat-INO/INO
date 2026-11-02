#include "v14_1_contract.hpp"
#include "landing_policy.h"
// Replace sample_landing with the team's shared portable decision function.
extern "C" int cansat_landing(double accel, double gyro, int stable_ms) {
    return sample_landing(accel, gyro, stable_ms);
}
