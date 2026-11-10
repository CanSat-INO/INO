#include "v14_1_contract.hpp"
#include "main_policy.h"
extern "C" int cansat_main(int landed, int gnss_fix, int target_visible, int fault) {
    return sample_main(landed, gnss_fix, target_visible, fault);
}
