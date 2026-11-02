#ifndef CANSAT_V14_PORTABLE_DECISION_H
#define CANSAT_V14_PORTABLE_DECISION_H
// Example portable decision function. Share this *header* with a real .ino only
// after review. No Arduino libraries, GPIO or CAN drivers are used here.
inline int example_policy(int module, int command, int landed) {
    if (module == 1 && command == 1) return landed ? 1 : 0;  // Main: landing
    if (module == 2 && command == 3) return landed ? 1 : 0;  // CAM: capture
    if (module == 3 && command == 2) return landed ? 1 : 0;  // Drive: move
    if (module == 3 && command == 4) return 1;                // Drive: stop
    return -1;                                                // unsupported
}
#endif
