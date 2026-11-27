#pragma once
#include <Arduino.h>

// TODO: Decode GNSS messages and validate position data.
class MaxM10M {
public:
    struct Data {
        bool valid = false;
        double latitude = 0.0;
        double longitude = 0.0;
        float altitudeM = 0.0f;
        uint8_t satellites = 0;
    };

    explicit MaxM10M(HardwareSerial &serial) : serial_(serial) {}
    void begin(uint32_t baud, int rxPin, int txPin);
    void update();
    const Data &data() const { return data_; }

private:
    HardwareSerial &serial_;
    Data data_;
};
