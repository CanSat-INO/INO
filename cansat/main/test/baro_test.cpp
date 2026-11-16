#include<Arduino.h>
#include<Wire.h>
#include"HP203B.h"

void setup(){
    Serial.begin(115200);
    Wire.begin();
}

void loop(){
    HP203B();
    delay(1000);
}
