"""Compile supplied Arduino decision functions, retaining byte-identical sources."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--profile',choices=['original','mission','guarded'],default='original');a=p.parse_args()
source=ROOT/'firmware/legacy_2025/original';out=ROOT/'firmware/sil/build'/a.profile;out.mkdir(parents=True,exist_ok=True)
main=(source/'cansat_main.ino').read_text(encoding='utf-8-sig')
globals=main[:main.index('void setup()')]
globals='\n'.join(line for line in globals.splitlines() if not line.lstrip().startswith('#include'))
loop=main[main.index('void loop()'):]
changes=[]
if a.profile in ('mission','guarded'):
    # The original 7 m switch can select camera guidance before the cone is large
    # enough to satisfy its fixed 2% threshold. Keep a separate explicit profile.
    loop=loop.replace('7.0','1.2')
    loop=loop.replace('dist <= 1.0','dist <= 0.5')
    loop=loop.replace('double angle = GoalAngle(currLat, currLon, goalLat, goalLon);','if(dist <= 0.5){ currPhase=6; stopmotor(); recorddata(dist,last_cam_res.ratio,last_cam_res.red_cogX,currentAction); delay(500); return; }\n    double angle = GoalAngle(currLat, currLon, goalLat, goalLon);')
    changes=['Camera-guidance switch: 7.0m -> 1.2m (demo parameter, not calibrated).','Goal radius: 1.0m -> 0.5m and explicit stop/return; no navigation after goal.']
prototypes='''void updateAllSensors();bool landed();void separate();void updateGNSS();double getDistance(double,double,double,double);double GoalAngle(double,double,double,double);double getYaw();void turntoGoal(double,double);void gpsnav();bool stack();void navcam();void goforward();void turnright();void turnleft();void goback();void stopmotor();void brakemotor();'''
runtime=r'''
int telemetry_count=0,returned_frame_records=0;
bool probe_mode=false;
void exchange(unsigned long wait){
 if(probe_mode){snapshot.ms+=wait;return;}
 std::cout<<"WAIT "<<wait<<" "<<currentAction<<" "<<mcp.pins[7]<<" "<<currPhase<<" "<<telemetry_count<<" "<<returned_frame_records<<std::endl;
 std::string line;if(!std::getline(std::cin,line)||line=="STOP")std::exit(0);
 std::istringstream in(line);if(!(in>>snapshot.ms>>snapshot.alt>>snapshot.temp>>snapshot.pres>>snapshot.lat>>snapshot.lon>>snapshot.yaw>>snapshot.ax>>snapshot.ay>>snapshot.az>>snapshot.image))std::exit(3);
}
void delay(unsigned long ms){exchange(ms);}
void recorddata(double,float,int,int,camera_fb_t* fb){++telemetry_count;if(fb&&frame_returned)++returned_frame_records;delay(100);}
'''
if a.profile=='guarded':
    loop=loop.replace('if(dist <= 0.5){ currPhase=6; stopmotor(); recorddata(dist,last_cam_res.ratio,last_cam_res.red_cogX,currentAction); delay(500); return; }',
        'if(dist <= 0.35){ stopmotor(); if(guard_goal_confirmed(dist)){currPhase=6; recorddata(dist,last_cam_res.ratio,last_cam_res.red_cogX,currentAction); delay(500);} else {currPhase=5; delay(100);} return; }\n    guard_goal_confirmed(dist);')
    loop=loop.replace('if (dist <= 0.5)', 'if (false)')
    runtime=r'''
int telemetry_count=0,returned_frame_records=0;
bool probe_mode=false,goal_latched=false;
cansat_sim::MissionGuard guard;
cansat_sim::GuardInput guard_input;
bool guard_goal_confirmed(double distance){
 static long last=-1;static unsigned count=0;
 if(guard_input.gnss_ms!=last){last=guard_input.gnss_ms;count=distance<=.35?count+1:0;}
 return count>=3;
}
void exchange(unsigned long wait){
 if(probe_mode){snapshot.ms+=wait;return;}
 unsigned health=guard.healthy(guard_input);
 bool drive=guard.stage==cansat_sim::MissionGuard::Landed && health==31 && !goal_latched;
 int action=drive?currentAction:0;
 int separation=guard.stage==cansat_sim::MissionGuard::Landed?mcp.pins[7]:0;
 std::cout<<"WAITG "<<wait<<" "<<action<<" "<<separation<<" "<<currPhase<<" "<<telemetry_count<<" "<<returned_frame_records<<" "<<int(guard.stage)<<" "<<health<<std::endl;
 std::string line;if(!std::getline(std::cin,line)||line=="STOP")std::exit(0);
 std::istringstream in(line);if(!(in>>snapshot.ms>>snapshot.alt>>snapshot.temp>>snapshot.pres>>snapshot.lat>>snapshot.lon>>snapshot.yaw>>snapshot.ax>>snapshot.ay>>snapshot.az>>snapshot.image))std::exit(3);
 guard_input.now=snapshot.ms;guard_input.altitude=snapshot.alt;
 guard_input.acceleration=std::sqrt(snapshot.ax*snapshot.ax+snapshot.ay*snapshot.ay+snapshot.az*snapshot.az);
 if(!(in>>guard_input.valid>>guard_input.barometer_ms>>guard_input.gnss_ms>>guard_input.imu_ms>>guard_input.heading_ms>>guard_input.camera_ms))guard_input.valid=0;
 guard.update(guard_input);
}
void delay(unsigned long ms){
 // Continue receiving timestamped sensors even inside last year's long waits.
 if(ms==0){exchange(0);return;}
 while(ms){unsigned long part=std::min(ms,100ul);exchange(part);ms-=part;}
}
void recorddata(double,float,int,int,camera_fb_t* fb){++telemetry_count;if(fb&&frame_returned)++returned_frame_records;delay(100);}
'''
    changes+=['Ground-referenced altitude: sustained descent before arming a 2s landing window.','Sensor validity/acquisition-time watchdog; gate motor output on missing/stale inputs.','Cooperative waits <=100ms; latch goal stop. No ESP32 SDK or pin emulation.','Goal: 3 distinct GNSS samples <=0.35m as provisional margin; simulator still verifies true distance <=0.5m.']
parts=['#include "arduino_shim.hpp"','#include "mission_guard.hpp"',globals,prototypes,runtime]
for name in ['motor.ino','landed_prepare.ino','navigation_stack.ino','camera_red.ino']:
    text=(source/name).read_text(encoding='utf-8-sig')
    if a.profile=='guarded' and name=='landed_prepare.ino':
        text=text.replace('bool landed(){','bool legacy_landed(){')+'\nbool landed(){return guard.stage==cansat_sim::MissionGuard::Landed;}\n'
    parts.append(text)
parts.append(loop)
entry=r'''
int main(int argc,char**argv){
 if(argc>1&&std::string(argv[1])=="--probe"){
  probe_mode=true;curralt=last_alt=20;total_acc=0;bool result=false;
  for(int i=0;i<10;++i)result=landed();
  std::cout<<"stationary_before_release_landed="<<result<<"\n";
  currLat=goalLat-.001;currLon=goalLon;stack();snapshot.ms=20000;
  std::cout<<"stationary_stuck_detected="<<stack()<<"\n";
  goforward();std::cout<<"forward_action="<<currentAction<<"\n";
  stopmotor();std::cout<<"stop_action="<<currentAction<<"\n";
  std::fill(camera_words.begin(),camera_words.end(),0);
  for(int y=0;y<120;++y)for(int x=72;x<88;++x)camera_words[y*160+x]=0xf800;
  frame.buf=reinterpret_cast<uint8_t*>(camera_words.data());frame.len=camera_words.size()*2;
  auto red=culcredcenter(&frame);std::cout<<"red_ratio="<<red.ratio<<"\nred_x="<<red.red_cogX<<"\n";
  isLanded=isSeparated=true;snapshot.lat=goalLat;snapshot.lon=goalLon;snapshot.yaw=90;snapshot.image="-";
  loop();std::cout<<"at_goal_phase="<<currPhase<<"\nat_goal_action="<<currentAction<<"\n";
  return 0;
 }
 exchange(0);last_alt=snapshot.alt;
 while(true){loop();std::cout<<"STATE "<<currPhase<<" "<<currentAction<<" "<<dist<<" "<<last_cam_res.ratio<<" "<<last_cam_res.red_cogX<<" "<<isLanded<<" "<<isSeparated<<std::endl;exchange(0);}
}
'''
if a.profile=='guarded':
    entry=entry.replace('while(true){loop();',r'''while(true){
 if(guard.stage!=cansat_sim::MissionGuard::Landed){stopmotor();currPhase=guard.stage==cansat_sim::MissionGuard::Waiting?0:1;delay(100);}
 else if(goal_latched){stopmotor();currPhase=6;delay(100);}
 else if(guard.healthy(guard_input)!=31){stopmotor();currPhase=8;delay(100);}
 else {loop();if(currPhase==6)goal_latched=true;}
''')
parts.append(entry)
cpp=out/'legacy.cpp';cpp.write_text('\n'.join(parts))
subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-I'+str(ROOT/'firmware/sil'),str(cpp),'-o',str(out/'legacy_sil')],check=True)
manifest={'profile':a.profile,'sources':{x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in source.glob('*.ino')},'changes':changes,'not_executed':['setup(): 600s startup wait, hardware initialization and camera register setup','record.ino: actual SD and UART writes (100ms telemetry wait retained)'],'shim':'Numeric sensor input, 160x120 RGB565 frame input, action/delay output; not MCU or I2C/SPI emulation.'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2));print(out/'legacy_sil')
