#ifndef DEMO_CAM_POLICY_H
#define DEMO_CAM_POLICY_H
// DEMO ONLY; uses mock recognition results, not live images.
inline int sample_cam(int visible, double ratio, double x) {
    if (!visible) return 0;
    if (ratio >= 0.5) return 4;
    if (x < -0.2) return 1;
    if (x > 0.2) return 2;
    return 3;
}
#endif
