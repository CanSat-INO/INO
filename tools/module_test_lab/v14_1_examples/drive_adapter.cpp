#include "v14_1_contract.hpp"
#include "drive_policy.h"
extern "C" int cansat_drive(int landed, int command, int obstacle, int emergency_stop) {
    return sample_drive(landed, command, obstacle, emergency_stop);
}
