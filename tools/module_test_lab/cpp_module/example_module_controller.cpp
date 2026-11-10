// Example v8.2 C++ control decisions for all three modules.
// Replace the pure logic while keeping the exported C function signature.
#include "controller_contract.h"

extern "C" int cansat_allow_command(int module, int command, int landed) {
    if (module == CANSAT_MAIN && command == CANSAT_LANDING) {
        return landed == 1 ? 1 : 0;
    }
    if (module == CANSAT_DRIVE && (command == CANSAT_MOVE || command == CANSAT_STOP)) {
        return 1;
    }
    if (module == CANSAT_CAM && command == CANSAT_CAPTURE) {
        return 1;
    }
    return -1;
}
