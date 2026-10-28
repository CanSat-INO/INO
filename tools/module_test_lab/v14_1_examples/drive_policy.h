#ifndef DEMO_DRIVE_POLICY_H
#define DEMO_DRIVE_POLICY_H
// DEMO ONLY; not an actuator command implementation.
inline int sample_drive(int landed, int command, int obstacle, int emergency_stop) {
    if (!landed || emergency_stop || obstacle) return 0;
    if (command >= 0 && command <= 3) return command;
    return 0;
}
#endif
