#ifndef DEMO_MAIN_POLICY_H
#define DEMO_MAIN_POLICY_H
// DEMO ONLY; not a complete CanSat flight state machine.
inline int sample_main(int landed, int gnss_fix, int target_visible, int fault) {
    if (fault) return 4;
    if (!landed) return 0;
    if (!gnss_fix) return 1;
    if (!target_visible) return 2;
    return 3;
}
#endif
