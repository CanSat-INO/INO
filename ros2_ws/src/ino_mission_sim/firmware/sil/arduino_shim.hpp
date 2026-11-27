#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
using std::abs; using std::max; using std::min;
constexpr double PI=3.141592653589793;
constexpr int HIGH=1,LOW=0,OUTPUT=1;
struct Snapshot { unsigned long ms=0; double alt=0,temp=20,pres=1013.25,lat=0,lon=0,yaw=90,ax=0,ay=0,az=0; std::string image="-"; } snapshot;
void delay(unsigned long ms);
unsigned long millis(){return snapshot.ms;}
struct Console { template<class T>void print(T){} template<class T>void println(T){} void println(){} } Serial;
struct WireType{} Wire;
struct HardwareSerial { explicit HardwareSerial(int){} template<class T>void println(T){} };
namespace imu { template<int N>struct Vector { double a,b,c;double x(){return a;}double y(){return b;}double z(){return c;} }; }
struct Adafruit_BMP280 { float readTemperature(){return snapshot.temp;}float readPressure(){return snapshot.pres*100;}float readAltitude(double){return snapshot.alt;} };
struct Adafruit_BNO055 { enum {VECTOR_LINEARACCEL,VECTOR_EULER};Adafruit_BNO055(int,int,WireType*){} imu::Vector<3> getVector(int kind){return kind==VECTOR_EULER?imu::Vector<3>{snapshot.yaw,0,0}:imu::Vector<3>{snapshot.ax,snapshot.ay,snapshot.az};} };
struct DFRobot_GNSSAndRTC_I2C { DFRobot_GNSSAndRTC_I2C(WireType*,int){} struct UTC{int hour=0,minute=0,second=0;};struct Date{int year=2026,month=1,date=1;};struct Lat{double latitudeDegree;};struct Lon{double lonitudeDegree;};UTC getUTC(){return {};}Date getDate(){return {};}Lat getLat(){return {snapshot.lat};}Lon getLon(){return {snapshot.lon};} };
struct Adafruit_MCP23X17 { std::array<int,16> pins{};void digitalWrite(int pin,int value){pins.at(pin)=value;}void pinMode(int,int){} };
struct camera_fb_t { uint8_t* buf=nullptr;size_t len=0;int width=160,height=120; };
inline std::vector<uint16_t> camera_words(160*120);
inline camera_fb_t frame;
inline bool frame_returned=false;
camera_fb_t* esp_camera_fb_get(){
 if(snapshot.image=="-")return nullptr;
 std::ifstream f(snapshot.image,std::ios::binary);if(!f.read(reinterpret_cast<char*>(camera_words.data()),camera_words.size()*2))return nullptr;
 frame.buf=reinterpret_cast<uint8_t*>(camera_words.data());frame.len=camera_words.size()*2;frame_returned=false;return &frame;
}
void esp_camera_fb_return(camera_fb_t*){frame_returned=true;}
