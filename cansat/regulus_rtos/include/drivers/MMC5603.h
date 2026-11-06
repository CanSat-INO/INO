#pragma once
#include <Arduino.h>
#include <Wire.h>

#define MMC5603_I2C_ADDR 0x30

// TODO: Implement the MMC5603 protocol using the datasheet.
class MMC5603 {
public:
    struct MagData { float magX = 0, magY = 0, magZ = 0; };
    explicit MMC5603(TwoWire &wire = Wire) : wire_(wire) {}
    bool begin();
    bool read(MagData &data);
private:
    TwoWire &wire_;
};
