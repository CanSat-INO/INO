#include<Wire.h>
#include<Arduino.h>
#include "HP203B.h"

void HP203B(){
    Wire.beginTransmission(0x76);
    Wire.write(0x48);
    byte error = Wire.endTransmission();

    if(error==0) {
        delay(33);
        Wire.beginTransmission(0x76);
        Wire.write(0x10);
        byte readError = Wire.endTransmission();

        if(readError==0){
        byte received = Wire.requestFrom(0x76, 6);
        if (received==6){
            byte pressureMSB=Wire.read();
            byte pressureCSB=Wire.read();
            byte pressureLSB=Wire.read();

            uint32_t rawPressure=((uint32_t)pressureMSB << 16)
                        |((uint32_t)pressureCSB << 8)
                        |pressureLSB;
            uint32_t rawPressure20 = rawPressure & 0xFFFFF;
            float pressure=rawPressure20/100.0f;


            Serial.print("Pressure: ");
            Serial.println(pressure);

        }
    }
        else Serial.println("Data reception failed");
    }
    else Serial.println("HP203B not found");

}