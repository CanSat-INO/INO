#pragma once
#include <Arduino.h>
#include <Wire.h>

// TODO: Implement the HP203B protocol using the datasheet.
class HP203B {
public:
    struct Data { float pressureHpa = 0; float temperatureC = 0; float altitudeM = 0; };
    explicit HP203B(TwoWire &wire = Wire) : wire_(wire) {}
    bool begin();
    bool read(Data &data);
private:
    TwoWire &wire_;
};
