#include "sim_port.hpp"
// Connection test only. This is not mission/autonomous flight software.
int main(){cansat_sim::Sensors input;cansat_sim::Actuators output;while(cansat_sim::wait(100,output,input)){} }
