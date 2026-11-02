// DEMO ONLY: adapter for a *shared* portable C++ policy; not real firmware.
#include "controller_contract.h"
#include "portable_decision.h"
extern "C" int cansat_allow_command(int module, int command, int landed) {
    return example_policy(module, command, landed);
}
