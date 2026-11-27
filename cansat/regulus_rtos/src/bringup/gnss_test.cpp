#include <Arduino.h>
#include "BoardConfig.h"
#include "drivers/MaxM10M.h"

HardwareSerial gnssSerial(1);
MaxM10M gnss(gnssSerial);

void setup() {
    Serial.begin(115200);
    gnss.begin(BoardConfig::GNSS_BAUD, BoardConfig::GNSS_RX, BoardConfig::GNSS_TX);
    Serial.printf("GNSS UART RX=%d TX=%d baud=%lu\n", BoardConfig::GNSS_RX,
                  BoardConfig::GNSS_TX, (unsigned long)BoardConfig::GNSS_BAUD);
}

void loop() {
    gnss.update();
    static uint32_t previous = 0;
    const uint32_t now = millis();
    if (now - previous < 500) return;
    previous = now;
    const MaxM10M::Data &d = gnss.data();
    Serial.printf("valid=%d lat=%.7f lon=%.7f alt=%.1f m sats=%u\n",
                  d.valid, d.latitude, d.longitude, d.altitudeM, d.satellites);
}
