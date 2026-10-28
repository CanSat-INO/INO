#include "v14_1_contract.hpp"
#include "cam_policy.h"
extern "C" int cansat_cam(int visible, double red_ratio, double x_offset) {
    return sample_cam(visible, red_ratio, x_offset);
}
