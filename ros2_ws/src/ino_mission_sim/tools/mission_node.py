"""Numerical virtual sensors -> native C++ firmware -> reduced-order mission plant."""
import argparse,copy,csv,json,math,os,selectors,subprocess,time
from pathlib import Path
import cv2,numpy as np,yaml
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data,QoSProfile,DurabilityPolicy
from rclpy.clock import Clock,ClockType
from geometry_msgs.msg import Twist,PoseStamped,Point
from nav_msgs.msg import Odometry,Path as PathMsg
from sensor_msgs.msg import Image
from std_msgs.msg import String,Bool
from visualization_msgs.msg import Marker
from cv_bridge import CvBridge
from rviz_mesh import ensure_stl
from descent_dynamics import Descent,world_to_body
from sensor_faults import SensorBank,NAMES

ROOT=Path(__file__).resolve().parents[1]
class Mission(Node):
    def __init__(self,cfg,out):
        super().__init__('legacy_mission',parameter_overrides=[rclpy.parameter.Parameter('use_sim_time',value=True)])
        self.cfg=cfg;self.out=Path(out);self.bridge=CvBridge();self.rng=np.random.default_rng(cfg['seed'])
        self.truth=None;self.yaw=0.;self.start=None;self.previous=None;self.vz=0.;self.v=0.;self.w=0.;self.accel=np.zeros(3);self.grounded=False
        self.action=0;self.phase=0;self.separation=0;self.released_parachute=False;self.pending=None;self.have_image=False;self.done=False
        self.reached=False;self.states=[];self.samples=[];self.events=[];self.image_count=0;self.frames_returned=0
        self.flight=Descent(cfg) if cfg.get('descent') else None
        self.flight_samples=[];self.flight_stage=None;self.landing=None;self.anomalies=[]
        self.pre_wait=float(cfg.get('pre_release_wait_s',0.));self.release_started=False
        if not math.isfinite(self.pre_wait) or self.pre_wait<0:raise ValueError('pre_release_wait_s must be nonnegative')
        self.signals=SensorBank(cfg['sensors'],cfg['seed']) if 'sensors' in cfg else None
        self.observed={};self.firmware_guard=None;self.command_rows=[];self.camera_rows=[];self.frame_serial=0;self.delivered_frame='-';self.frame_paths=[]
        self.sensor_log=(self.out/'sensor_packets.jsonl').open('w') if self.signals else None
        self.phase_names={0:'待機・放出',1:'降下判定',2:'着地判定',3:'分離',4:'GNSS誘導',5:'赤色カメラ誘導',6:'ゴール判定',8:'センサー異常による停止'}
        self.vel_pub=self.create_publisher(Twist,'/mission/plant/cmd_vel',10)
        self.sensors_pub=self.create_publisher(String,'/mission/virtual_sensors',10)
        self.status_pub=self.create_publisher(String,'/mission/status',10)
        latched=QoSProfile(depth=10,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.marker_pub=self.create_publisher(Marker,'/mission/robot_marker',latched)
        self.path_pub=self.create_publisher(PathMsg,'/mission/truth/path',latched);self.path=PathMsg();self.path.header.frame_id='world'
        self.subs=[self.create_subscription(Odometry,'/ground_truth/odom',self.odometry,10),self.create_subscription(Image,'/raw/left/image',self.camera,10)]
        self.subs.append(self.create_subscription(Bool,'/mission/parachute/deploy',self.deploy_command,10))
        binary=Path(cfg['controller_executable']) if cfg.get('controller_executable') else ROOT/'firmware/sil/build'/cfg['profile']/'legacy_sil'
        self.stderr=(self.out/'firmware.stderr').open('w')
        self.proc=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,bufsize=1)
        self.selector=selectors.DefaultSelector();self.selector.register(self.proc.stdout,selectors.EVENT_READ)
        self.timer=self.create_timer(.02,self.tick)
        self.wall_start=time.monotonic()
        self.watchdog_timer=self.create_timer(.5,self.watchdog,clock=Clock(clock_type=ClockType.STEADY_TIME))

    def watchdog(self):
        if self.done:return
        if self.truth is None and time.monotonic()-self.wall_start>90:self.finish('sensor_start_timeout')
        elif time.monotonic()-self.wall_start>max(180,self.cfg['duration_s']*12):self.finish('wall_time_limit')

    def now(self):return self.get_clock().now().nanoseconds/1e9
    def flight_time(self):return max(0.,self.now()-self.start-self.pre_wait)
    def deploy_command(self,msg):
        if msg.data and self.flight and self.start is not None and not self.grounded and not self.done:
            if self.now()-self.start>=self.pre_wait:self.flight.deploy(self.flight_time())

    def separation_command(self):
        if not self.separation or self.released_parachute:return
        self.released_parachute=True
        if self.flight:
            if not self.grounded:
                self.anomalies.append(dict(event='separation_while_airborne',time_s=self.now()-self.start,altitude_m=self.truth.pose.pose.position.z))
            if self.flight.chute.get('detach_on_separation',True):
                self.flight.detach();self.flight_stage='detached'
                self.events.append(dict(event='parachute_detached',time=self.now()-self.start,altitude_m=self.truth.pose.pose.position.z))
    def odometry(self,msg):
        if self.done:return
        self.truth=msg; q=msg.pose.pose.orientation
        self.yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
        if self.start is None:
            self.start=self.now();self.previous=self.now();self.get_logger().info('Virtual sensor input active; mission clock started')
        if len(self.samples)==0 or self.now()-self.samples[-1][0]>.09:
            p=msg.pose.pose.position;self.samples.append([self.now(),p.x,p.y,p.z,self.yaw,self.phase,self.action,int(self.grounded)])
            if self.flight:
                f=self.flight.info(self.flight_time())
                self.flight_samples.append([self.now()-self.start,p.x,p.y,p.z,*f['velocity_enu_mps'],*f['wind_enu_mps'],f['open_fraction'],f['cda_m2'],int(self.grounded)])
            pose=PoseStamped();pose.header.frame_id='world';pose.header.stamp=msg.header.stamp;pose.pose=copy.deepcopy(msg.pose.pose)
            self.path.header.stamp=msg.header.stamp;self.path.poses.append(pose);self.path_pub.publish(self.path)
            marker=Marker();marker.header.frame_id='world';marker.id=0;marker.type=Marker.MESH_RESOURCE;marker.action=Marker.ADD;marker.mesh_resource=ensure_stl('deployed').as_uri();marker.scale.x=marker.scale.y=marker.scale.z=1.;marker.color.r=.8;marker.color.g=.8;marker.color.b=.85;marker.color.a=1.;marker.pose=copy.deepcopy(msg.pose.pose);self.marker_pub.publish(marker)
            text=Marker();text.header.frame_id='world';text.id=1;text.type=Marker.TEXT_VIEW_FACING;text.action=Marker.ADD;text.pose.position=copy.deepcopy(p);text.pose.position.z+=.5;text.pose.orientation.w=1.;text.scale.z=.22;text.color.r=text.color.g=text.color.b=text.color.a=1.;text.text=f"phase {self.phase} | action {self.action} | t={self.now()-self.start:.1f}s";self.marker_pub.publish(text)
            fraction=self.flight.fraction if self.flight else (0. if self.released_parachute else 1.)
            canopy=Marker();canopy.header.frame_id='world';canopy.id=2;canopy.type=Marker.SPHERE;canopy.action=Marker.ADD if fraction>.001 else Marker.DELETE;canopy.pose.position=copy.deepcopy(p);canopy.pose.position.z+=1.2;canopy.pose.orientation.w=1.;canopy.scale.x=canopy.scale.y=max(.001,self.cfg['parachute_diameter_m']*math.sqrt(fraction));canopy.scale.z=max(.001,.15*math.sqrt(fraction));canopy.color.r=1.;canopy.color.g=.45;canopy.color.b=.05;canopy.color.a=.8;self.marker_pub.publish(canopy)
            if self.flight:
                wind=self.flight.wind(self.flight_time())
                arrow=Marker();arrow.header.frame_id='world';arrow.id=3;arrow.type=Marker.ARROW;arrow.action=Marker.ADD;arrow.pose.orientation.w=1.;arrow.scale.x=.04;arrow.scale.y=.1;arrow.scale.z=.15;arrow.color.g=1.;arrow.color.b=1.;arrow.color.a=1.
                arrow.points=[Point(x=p.x,y=p.y,z=p.z+1.6),Point(x=p.x+.3*wind[0],y=p.y+.3*wind[1],z=p.z+1.6+.3*wind[2])];self.marker_pub.publish(arrow)

    def camera(self,msg):
        rgb=self.bridge.imgmsg_to_cv2(msg,'rgb8');small=cv2.resize(rgb,(160,120),interpolation=cv2.INTER_AREA).astype(np.uint16)
        words=((small[:,:,0]>>3)<<11)|((small[:,:,1]>>2)<<5)|(small[:,:,2]>>3)
        if self.signals:
            if self.start is not None:
                stamp=msg.header.stamp.sec+msg.header.stamp.nanosec/1e9-self.start
                if stamp>=0:self.signals.channels['camera'].push(stamp,words.astype('<u2').tobytes())
        else:
            temp=self.out/'frame.tmp';words.astype('<u2').tofile(temp);temp.replace(self.out/'frame.rgb565')
        self.have_image=True;self.image_count+=1
        if self.image_count==1:cv2.imwrite(str(self.out/'release-left.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        if self.image_count%20==0:cv2.imwrite(str(self.out/'latest-left.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))

    def sensor_packet(self):
        if self.signals:return self.observed_packet()
        p=self.truth.pose.pose.position;gx,gy=self.cfg['goal_xy_m'];noise=self.rng.normal(0,self.cfg['gnss_noise_std_m'],2)
        # Preserve last year's goal coordinates. Define a documented local ENU
        # origin so they correspond to the goal cone, not to a real flight site.
        lat=30.3742226+(p.y-gy+noise[1])/110946.252
        lon=130.9599762+(p.x-gx+noise[0])/(111320*math.cos(math.radians(lat)))
        heading=(90-math.degrees(self.yaw)+self.rng.normal(0,self.cfg['heading_noise_std_deg']))%360
        altitude=max(0.,p.z);pressure=1013.25*max(.01,1-altitude/44330.)**5.255
        packet=dict(time_ms=round((self.now()-self.start)*1000),altitude_m=altitude,temperature_c=20.,pressure_hpa=pressure,latitude_deg=lat,longitude_deg=lon,heading_deg=heading,linear_accel_mps2=self.accel.tolist(),frame=str(self.out/'frame.rgb565') if self.have_image else '-')
        if self.flight:packet['descent']=self.flight.info(self.flight_time())
        return packet

    def sample_sensors(self):
        t=self.now()-self.start;p=self.truth.pose.pose.position
        values=dict(barometer=[max(0.,p.z),20.,1013.25*max(.01,1-max(0.,p.z)/44330.)**5.255],gnss=[p.x,p.y],imu=self.accel,heading=[(90-math.degrees(self.yaw))%360])
        for name,value in values.items():self.signals.channels[name].push(t,value)
        self.observed=self.signals.read(t)
        camera=self.observed['camera']
        if camera['value'] is not None and camera['serial']!=self.frame_serial:
            self.frame_serial=camera['serial'];folder=self.out/'sensor-frames';folder.mkdir(exist_ok=True)
            path=folder/f"frame-{self.frame_serial:06d}.rgb565";path.write_bytes(camera['value']);self.delivered_frame=str(path);self.frame_paths.append(path)
            # Immutable acquisition/delivery pairs; retain the latest 60 seconds
            # at 10 Hz by default. Optional keep_camera_frames retains all files.
            if not self.cfg.get('keep_camera_frames',False) and len(self.frame_paths)>600:self.frame_paths.pop(0).unlink(missing_ok=True)
            self.camera_rows.append([camera['stamp_s'],t,camera['age_s'],self.delivered_frame])

    def observed_packet(self):
        def value(name,fallback):return self.observed[name]['value'] if self.observed[name]['value'] is not None else fallback
        alt,temp,pres=value('barometer',[0.,20.,1013.25]);x,y=value('gnss',[0.,0.]);gx,gy=self.cfg['goal_xy_m']
        lat=30.3742226+(y-gy)/110946.252;lon=130.9599762+(x-gx)/(111320*math.cos(math.radians(lat)))
        metadata={name:{key:sample[key] for key in ['stamp_s','age_s','valid']} for name,sample in self.observed.items()}
        mask=sum(1<<i for i,name in enumerate(NAMES) if metadata[name]['valid'])
        stamps=[round(metadata[name]['stamp_s']*1000) if metadata[name]['stamp_s'] is not None else -1 for name in NAMES]
        return dict(time_ms=round((self.now()-self.start)*1000),altitude_m=float(alt),temperature_c=float(temp),pressure_hpa=float(pres),latitude_deg=float(lat),longitude_deg=float(lon),heading_deg=float(value('heading',[0.])[0])%360,linear_accel_mps2=list(map(float,value('imu',[0.,0.,0.]))),frame=self.delivered_frame if metadata['camera']['valid'] else '-',sensor_meta=metadata,valid_mask=mask,sample_stamps_ms=stamps)

    def reply(self):
        s=self.sensor_packet();line=[s['time_ms'],s['altitude_m'],s['temperature_c'],s['pressure_hpa'],s['latitude_deg'],s['longitude_deg'],s['heading_deg'],*s['linear_accel_mps2'],s['frame']]
        if self.signals:
            line += [s['valid_mask'],*s['sample_stamps_ms']];self.sensor_log.write(json.dumps(s)+'\n')
        self.proc.stdin.write(' '.join(map(str,line))+'\n');self.proc.stdin.flush();self.sensors_pub.publish(String(data=json.dumps(s)));self.pending=None

    def tick(self):
        if self.done:self.vel_pub.publish(Twist());return
        if self.truth is None:return
        if (self.out/'stop.request').exists():self.finish('user_stop');return
        now=self.now();dt=max(0.,now-self.previous);dt=dt if self.flight else min(.05,dt);self.previous=now;p=self.truth.pose.pose.position
        elapsed=now-self.start
        if elapsed>=self.pre_wait and not self.release_started:
            self.release_started=True;self.events.append(dict(event='release',time=elapsed))
        if self.flight and self.release_started and not self.grounded and (self.out/'deploy.request').exists():self.flight.deploy(self.flight_time())
        if p.z<.015 and elapsed>self.pre_wait+1 and not self.grounded:
            self.grounded=True;self.events.append(dict(event='ground_contact',time=now-self.start));self.vz=0.
            if self.flight:
                velocity=self.flight.velocity.copy()
                self.landing=dict(time_s=now-self.start,position_m=[p.x,p.y,p.z],drift_m=math.hypot(p.x,p.y),precontact_model_velocity_enu_mps=velocity.tolist(),vertical_speed_mps=abs(float(velocity[2])),horizontal_speed_mps=float(np.linalg.norm(velocity[:2])),kinetic_energy_j=float(.5*self.cfg['mass_kg']*np.dot(velocity,velocity)),open_fraction=self.flight.fraction)
                self.flight.velocity[:]=0.
        az=0.
        air_velocity=None;air_accel=None
        if not self.release_started:pass
        elif not self.grounded and self.flight:
            air_velocity,air_accel=self.flight.advance(self.flight_time(),min(dt,self.flight_time()),p.z)
            if self.flight.stage!=self.flight_stage:
                self.events.append(dict(event='parachute_'+self.flight.stage,time=now-self.start,altitude_m=p.z));self.flight_stage=self.flight.stage
        elif not self.grounded:
            k=.5*self.cfg['air_density_kgm3']*self.cfg['drag_coefficient']*math.pi*(self.cfg['parachute_diameter_m']/2)**2/self.cfg['mass_kg']
            # Small substeps keep the vertical force integration stable.
            old=self.vz
            for _ in range(5):self.vz+=(-9.81-k*self.vz*abs(self.vz))*dt/5
            az=(self.vz-old)/dt if dt else 0.
        else:self.vz=0.
        if hasattr(self,'motor_pair'):
            left,right=self.motor_pair
        else:left,right={1:(1.,1.),2:(1.,-1.),3:(-1.,1.)}.get(self.action,(0.,0.))
        target_v=self.cfg['speed_mps']*(left+right)/2 if self.grounded else 0.
        target_w=self.cfg['turn_rate_radps']*(right-left)/2 if self.grounded else 0.
        old=self.v;alpha=min(1.,dt/self.cfg['motor_tau_s']);self.v+=(target_v-self.v)*alpha;self.w+=(target_w-self.w)*alpha
        self.accel=np.array([(self.v-old)/dt if dt else 0.,self.v*self.w,az])
        cmd=Twist();cmd.linear.x=self.v;cmd.linear.z=self.vz;cmd.angular.z=self.w
        if air_velocity is not None:
            body=world_to_body(air_velocity,self.yaw);cmd.linear.x,cmd.linear.y,cmd.linear.z=map(float,body);cmd.angular.z=0.
            self.accel=world_to_body(air_accel,self.yaw)
        self.vel_pub.publish(cmd)
        if self.signals:self.sample_sensors()
        if self.pending is not None and now>=self.pending:self.reply()
        # One line per tick avoids TextIO buffering hiding a second complete line
        # from select(); the child waits for the reply before producing more.
        if self.pending is None and self.selector.select(timeout=0):
            line=self.proc.stdout.readline().strip();fields=line.split()
            if not fields:self.finish('firmware_exit');return
            if fields[0] in ('WAIT','WAITG'):self.accept_wait(fields,now)
            elif fields[0]=='WAIT2':
                wait,left,right,separation,phase=map(float,fields[1:]);self.motor_pair=(max(-1.,min(1.,left)),max(-1.,min(1.,right)));self.separation=int(separation);self.phase=int(phase);self.pending=now+max(0.,wait)/1000.
                if wait==0:self.reply()
            elif fields[0]=='STATE':
                phase,action=int(fields[1]),int(fields[2]);distance=float(fields[3]);self.states.append(dict(time=now-self.start,phase=phase,action=action,distance=distance,red_ratio=float(fields[4]),red_x=int(fields[5])))
                if phase==6 and action==0:
                    distance=math.hypot(p.x-self.cfg['goal_xy_m'][0],p.y-self.cfg['goal_xy_m'][1])
                    if distance<=(.5 if self.cfg['profile']=='guarded' else .55):self.reached=True;self.finish('goal_stopped');return
                    if self.cfg['profile']=='guarded':self.finish('false_goal_stop');return
                # STATE is followed immediately by WAIT. Read it directly: the
                # native host writes both without waiting for another input.
                line=self.proc.stdout.readline().split()
                if line and line[0] in ('WAIT','WAITG'):self.accept_wait(line,now)
        self.separation_command()
        state=dict(elapsed_s=now-self.start,phase=self.phase,phase_name=self.phase_names.get(self.phase,'不明'),action=self.action,altitude_m=max(0.,p.z),grounded=self.grounded,parachute_release_command=self.released_parachute,profile=self.cfg['profile'],truth_distance_m=math.hypot(p.x-self.cfg['goal_xy_m'][0],p.y-self.cfg['goal_xy_m'][1]))
        if self.flight:
            state['descent']=self.flight.info(self.flight_time());state['position_enu_m']=[p.x,p.y,p.z];state['parachute_diameter_m']=self.cfg['parachute_diameter_m'];state['released']=self.release_started;state['release_elapsed_s']=self.flight_time()
        if self.firmware_guard:state['firmware_guard']=self.firmware_guard
        if self.states:state['last_firmware_state']=self.states[-1]
        temp=self.out/'status.tmp';temp.write_text(json.dumps(state,ensure_ascii=False));temp.replace(self.out/'status.json');self.status_pub.publish(String(data=json.dumps(state,ensure_ascii=False)))
        if self.cfg.get('stop_when_firmware_landed') and self.firmware_guard and self.firmware_guard['stage']==2:self.finish('landing_confirmed')
        elif self.grounded and self.cfg.get('stop_on_landing',False):self.finish('landed')
        elif now-self.start>=self.cfg['duration_s']:self.finish('time_limit')
        elif max(abs(p.x),abs(p.y))>self.cfg['geofence_m']:self.finish('geofence')
        elif hasattr(self,'motor_pair') and self.phase==6 and max(abs(x) for x in self.motor_pair)<1e-6 and self.grounded and state['truth_distance_m']<=.55:self.reached=True;self.finish('goal_stopped')

    def accept_wait(self,fields,now):
        wait,self.action,self.separation,self.phase,telemetry,self.frames_returned=map(int,fields[1:7])
        if fields[0]=='WAITG':self.firmware_guard=dict(stage=int(fields[7]),health_mask=int(fields[8]))
        self.command_rows.append([now-self.start,self.action,self.separation,self.phase,self.firmware_guard['stage'] if self.firmware_guard else -1,self.firmware_guard['health_mask'] if self.firmware_guard else -1])
        self.pending=now+wait/1000.
        if wait==0:self.reply()

    def finish(self,reason):
        if self.done:return
        self.get_logger().info('Mission finished: '+reason)
        self.done=True;self.vel_pub.publish(Twist())
        try:self.proc.stdin.write('STOP\n');self.proc.stdin.flush();self.proc.wait(timeout=2)
        except (BrokenPipeError,subprocess.TimeoutExpired):self.proc.terminate()
        result=dict(reason=reason,goal_stopped=self.reached,profile=self.cfg['profile'],elapsed_s=self.now()-(self.start if self.start is not None else self.now()),ground_contact=self.grounded,parachute_release_command=self.released_parachute,phases=sorted(set([x['phase'] for x in self.states]+[x[5] for x in self.samples])),states=self.states,events=self.events,image_frames=self.image_count,returned_frame_records=self.frames_returned)
        result['pre_release_wait_s']=self.pre_wait
        if self.signals:
            result['sensor_counts']=self.signals.counts();self.sensor_log.close()
        for filename,header,rows in [('firmware_commands.csv',['time_s','action','separation','phase','guard_stage','health_mask'],self.command_rows),('camera_delivery.csv',['capture_time_s','delivery_time_s','age_s','frame'],self.camera_rows)]:
            with (self.out/filename).open('w',newline='') as file:
                writer=csv.writer(file);writer.writerow(header);writer.writerows(rows)
        if self.flight:
            result.update(landing=self.landing,anomalies=self.anomalies,descent_model='3D point mass; velocity-driven Gazebo; no attitude/cloth/contact-impact model')
            with (self.out/'descent.csv').open('w',newline='') as f:
                w=csv.writer(f);w.writerow(['time_s','x','y','z','model_vx','model_vy','model_vz','wind_e','wind_n','wind_u','open_fraction','cda_m2','grounded']);w.writerows(self.flight_samples)
        if self.truth:
            p=self.truth.pose.pose.position;result['final_position_m']=[p.x,p.y,p.z];result['final_goal_distance_m']=math.hypot(p.x-self.cfg['goal_xy_m'][0],p.y-self.cfg['goal_xy_m'][1])
        (self.out/'result.json').write_text(json.dumps(result,indent=2));
        with (self.out/'trajectory.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['sim_time','x','y','z','yaw','phase','action','grounded']);w.writerows(self.samples)

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args();cfg=yaml.safe_load(Path(a.config).read_text())
    import faulthandler,signal
    faulthandler.register(signal.SIGUSR1)
    rclpy.init();node=Mission(cfg,a.output)
    node.get_logger().info('Mission ready: waiting for clock, odometry and camera')
    try:
        while rclpy.ok() and (not node.done or cfg.get('keep_open',False)):rclpy.spin_once(node,timeout_sec=.05)
    except KeyboardInterrupt:node.finish('interrupted')
    finally:
        if not node.done:node.finish('shutdown')
        node.destroy_node();rclpy.try_shutdown()
if __name__=='__main__':main()
