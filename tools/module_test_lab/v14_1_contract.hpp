#ifndef CANSAT_V14_1_HOST_CONTRACT_HPP
#define CANSAT_V14_1_HOST_CONTRACT_HPP
// Host-only portable decision contracts. Not a firmware/hardware interface.
// 0/1 means no/yes for bool-like inputs. See v14.1 README for output meanings.
extern "C" int cansat_landing(double accel_mps2, double gyro_dps, int stable_ms);
extern "C" int cansat_drive(int landed, int command, int obstacle, int emergency_stop);
extern "C" int cansat_cam(int visible, double red_ratio, double x_offset);
extern "C" int cansat_main(int landed, int gnss_fix, int target_visible, int fault);
#endif
