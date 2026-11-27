#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
export ROS_DOMAIN_ID=${INO_DRIVE_TEST_DOMAIN:-86} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
source scripts/sim-environment.sh
work="$(mktemp -d)"
echo "$work"
g++ -std=c++17 examples/module_adapters/adapter.cpp -o "$work/adapter"
pids=()
cleanup() {
 for pid in "${pids[@]}"; do kill -TERM -- "-$pid" 2>/dev/null || true; done
 for _ in {1..80}; do
   alive=false
   for pid in "${pids[@]}"; do
     if kill -0 -- "-$pid" 2>/dev/null; then alive=true; fi
   done
   if ! $alive; then break; fi
   sleep 0.1
 done
 for pid in "${pids[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
 wait || true
}
trap cleanup EXIT
setsid bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh runtime:="$work" drive:=true bench:=drive > "$work/sim.log" 2>&1 &
pids+=("$!")
ino_sim_wait
setsid python3 examples/module_adapters/connect.py drive "$work/adapter" > "$work/drive.log" 2>&1 &
pids+=("$!")
python3 - <<'PY' | tee "$work/metrics.log"
import json, math, time, rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data
rclpy.init()
node=rclpy.create_node('release_drive_check')
state={}
gate_stops = 0

def gate_update(msg):
    global gate_stops
    previous = state.get('gate')
    if previous and (previous.linear.x or previous.angular.z) and not (msg.linear.x or msg.angular.z):
        gate_stops += 1
    state['gate'] = msg

node.create_subscription(Clock, '/clock',
    lambda msg: state.update(sim_ns=msg.clock.sec*10**9+msg.clock.nanosec), qos_profile_sensor_data)
for key, topic in [('truth','/ground_truth/odom'),('encoder','/ground/encoder_odom')]:
    node.create_subscription(Odometry,topic,lambda msg,k=key:state.update({k:msg}),qos_profile_sensor_data)
node.create_subscription(Twist,'/virtual/internal_drive',gate_update,10)
pub=node.create_publisher(String,'/bench/scenario',10)
def wait(seconds, drive=None):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if drive:
            pub.publish(String(data=json.dumps(dict(kind='drive',linear_mps=drive[0],angular_radps=drive[1]))))
        rclpy.spin_once(node,timeout_sec=.07)
def stopped():
    return state['gate'].linear.x == 0 and state['gate'].angular.z == 0

def wait_stopped():
    for _ in range(20):
        wait(.1)
        if stopped():
            return
    raise AssertionError('No zero command observed after stopping')

def drive_for_sim(seconds, drive):
    wall_start = time.monotonic()
    sim_start = state['sim_ns']
    previous = sim_start
    while state['sim_ns'] - sim_start < seconds * 10**9:
        if time.monotonic() - wall_start > 75:
            raise RuntimeError('Simulation time did not advance enough during drive')
        wait(.05, drive)
        if state['sim_ns'] < previous:
            raise RuntimeError('Simulation clock reset during drive')
        previous = state['sim_ns']
    return (state['sim_ns']-sim_start)/1e9, time.monotonic()-wall_start

def pose():
    p=state['truth'].pose.pose
    q=p.orientation
    return p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
def angle(a,b):
    return math.atan2(math.sin(b-a),math.cos(b-a))
for _ in range(50):
    wait(1)
    if {'truth','encoder','gate','sim_ns'} <= state.keys():
        break
assert {'truth','encoder','gate','sim_ns'} <= state.keys(),state.keys()
for label,command in [('forward',(.10,0)),('reverse',(-.10,0)),('left',(0,.35)),('right',(0,-.35))]:
    before=pose()
    enc_before=state['encoder'].pose.pose.position
    stops_before = gate_stops
    sim_s, wall_s = drive_for_sim(2.0, command)
    after=pose()
    enc_after=state['encoder'].pose.pose.position
    displacement=math.dist(before[:2],after[:2])
    enc_displacement=math.hypot(enc_after.x-enc_before.x,enc_after.y-enc_before.y)
    yaw=angle(before[2],after[2])
    signed_distance=(after[0]-before[0])*math.cos(before[2])+(after[1]-before[1])*math.sin(before[2])
    unexpected_stops = gate_stops - stops_before
    print(label, json.dumps(dict(linear_mps=command[0], angular_radps=command[1],
        requested_sim_s=2.0, sim_s=round(sim_s, 4), wall_s=round(wall_s, 4),
        rtf=round(sim_s/wall_s, 4), truth_m=round(displacement, 4),
        encoder_m=round(enc_displacement, 4), truth_yaw_rad=round(yaw, 4),
        unintended_gate_stops=unexpected_stops)), flush=True)
    if command[0]:
        assert signed_distance*math.copysign(1,command[0]) > .003
    else:
        assert yaw*math.copysign(1,command[1]) > .01
    wait_stopped()
extra=node.create_publisher(Twist,'/cmd_vel',10)
wait(.8,(.10,0))
assert state['gate'].linear.x==0
node.destroy_publisher(extra)
wait(.7)
assert state['gate'].linear.x==0
wait(1,(.10,0))
assert state['gate'].linear.x>0
wait(1,(0,0))
assert state['gate'].linear.x==0 and state['gate'].angular.z==0
print('timeout, duplicate, stopped before fresh command, resumed, explicit stop verified; gate_stop_events=', gate_stops, flush=True)
node.destroy_node()
rclpy.shutdown()
PY
