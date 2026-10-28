#ifndef DEMO_LANDING_POLICY_H
#define DEMO_LANDING_POLICY_H
// DEMO ONLY. NOT A VERIFIED LANDING DETECTOR or flight criterion.
inline int sample_landing(double accel, double gyro, int stable_ms) {
    return accel >= 15.0 && gyro <= 5.0 && stable_ms >= 600 ? 1 : 0;
}
#endif
