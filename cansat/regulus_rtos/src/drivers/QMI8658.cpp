#include "drivers/QMI8658.h"

bool QMI8658::begin() {
    // TODO: Confirm identity and configure acceleration/gyro measurement.
    return false;
}

bool QMI8658::read(Data &data) {
    // TODO: Read raw axes and convert to m/s2 and deg/s.
    (void)data;
    return false;
}
