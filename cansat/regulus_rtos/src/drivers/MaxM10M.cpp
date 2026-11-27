#include "drivers/MaxM10M.h"

void MaxM10M::begin(uint32_t baud, int rxPin, int txPin) {
    serial_.begin(baud, SERIAL_8N1, rxPin, txPin);
}

void MaxM10M::update() {
    // TODO: Consume incoming bytes and decode position, altitude and fix status.
    // Keep data_.valid false until a complete, valid fix has been received.
    while (serial_.available()) {
        (void)serial_.read();
    }
}
