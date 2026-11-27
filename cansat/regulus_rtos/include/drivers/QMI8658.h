#pragma once
#include <Arduino.h>
#include <Wire.h>

// TODO: Implement the QMI8658 protocol using the datasheet.
class QMI8658 {
public:
    static constexpr uint8_t ADDRESS_LOW = 0x6A;
    static constexpr uint8_t ADDRESS_HIGH = 0x6B;
    struct Data { float ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0; };
    explicit QMI8658(TwoWire &wire = Wire, uint8_t address = ADDRESS_LOW)
        : wire_(wire), address_(address) {}
    bool begin();
    bool read(Data &data);
    uint8_t address() const { return address_; }
private:
    TwoWire &wire_;
    uint8_t address_;
};
