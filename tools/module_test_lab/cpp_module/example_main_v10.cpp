// v10 sample: a PC-testable portion of Main landing judgment.
// Only one C++ source is linked at a time; not a firmware image.
#include "controller_contract.h"
extern "C" int cansat_allow_command(int module, int command, int landed) {
    if (module != CANSAT_MAIN || command != CANSAT_LANDING) return -1;
    return landed == 1 ? 1 : 0;
}
