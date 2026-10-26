// v10 sample: Drive's decisions on MOVE and STOP.
#include "controller_contract.h"
extern "C" int cansat_allow_command(int module, int command, int landed) {
    (void)landed;
    if (module != CANSAT_DRIVE) return -1;
    if (command == CANSAT_MOVE || command == CANSAT_STOP) return 1;
    return -1;
}
