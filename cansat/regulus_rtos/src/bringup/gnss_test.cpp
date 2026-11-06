#include <Arduino.h>
#include "BoardConfig.h"

// UART connection test: print incoming NMEA sentences before adding a GNSS driver.
HardwareSerial gnssSerial(1);

void setup() {
    Serial.begin(115200);
    gnssSerial.begin(BoardConfig::GNSS_BAUD, SERIAL_8N1,
                     BoardConfig::GNSS_RX, BoardConfig::GNSS_TX);
    Serial.printf("GNSS UART RX=%d TX=%d baud=%lu\n", BoardConfig::GNSS_RX,
                  BoardConfig::GNSS_TX, (unsigned long)BoardConfig::GNSS_BAUD);
}

void loop() {
    while (gnssSerial.available()) Serial.write(gnssSerial.read());
}
