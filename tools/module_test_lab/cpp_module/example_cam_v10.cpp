// v10 sample: CAM's decision on CAPTURE.
#include "controller_contract.h"
extern "C" int cansat_allow_command(int module, int command, int landed) {
    (void)landed;
    if (module != CANSAT_CAM || command != CANSAT_CAPTURE) return -1;
    return 1;
}
