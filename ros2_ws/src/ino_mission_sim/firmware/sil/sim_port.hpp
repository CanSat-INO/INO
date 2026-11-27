#pragma once
// Future host-buildable controllers can use the same virtual sensor contract.
// No Arduino, ESP-IDF, GPIO, or ROS headers are required by this adapter.
#include <iostream>
#include <sstream>
#include <string>
namespace cansat_sim {
struct Sensors {
 unsigned long time_ms;double altitude_m,temperature_c,pressure_hpa,latitude_deg,longitude_deg,heading_deg,ax,ay,az;std::string rgb565_file;
 unsigned valid_mask=0;long barometer_ms=-1,gnss_ms=-1,imu_ms=-1,heading_ms=-1,camera_ms=-1;
};
struct Actuators { double left=0,right=0;bool separate=false;int phase=0; };
inline bool wait(unsigned long delay_ms,const Actuators& out,Sensors& in){
 std::cout<<"WAIT2 "<<delay_ms<<" "<<out.left<<" "<<out.right<<" "<<out.separate<<" "<<out.phase<<std::endl;
 std::string line;if(!std::getline(std::cin,line)||line=="STOP")return false;
 std::istringstream stream(line);
 if(!(stream>>in.time_ms>>in.altitude_m>>in.temperature_c>>in.pressure_hpa>>in.latitude_deg>>in.longitude_deg>>in.heading_deg>>in.ax>>in.ay>>in.az>>in.rgb565_file))return false;
 // Older packets have no validity metadata. Keep legacy readers compatible,
 // but never declare an un-timestamped packet healthy to a new controller.
 if(!(stream>>in.valid_mask>>in.barometer_ms>>in.gnss_ms>>in.imu_ms>>in.heading_ms>>in.camera_ms)){
   in.valid_mask=0;in.barometer_ms=in.gnss_ms=in.imu_ms=in.heading_ms=in.camera_ms=-1;
 }
 return true;
}
}
