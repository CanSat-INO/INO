#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source scripts/ros-environment.sh
export ROS_DOMAIN_ID=${INO_DRIVE_TEST_DOMAIN:-86} ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
work="$(mktemp -d)"
echo "$work"
g++ -std=c++17 examples/module_adapters/adapter.cpp -o "$work/adapter"
pids=()
cleanup() {
 for pid in "${pids[@]}"; do kill -INT -- "-$pid" 2>/dev/null || true; done
 wait || true
}
trap cleanup EXIT
setsid bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh runtime:="$work" drive:=true bench:=drive > "$work/sim.log" 2>&1 &
pids+=("$!")
setsid python3 examples/module_adapters/connect.py drive "$work/adapter" > "$work/drive.log" 2>&1 &
pids+=("$!")
python3 - <<'PY'
import json, math, time, rclpy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from rclpy.qos import qos_profile_sensor_data
rclpy.init()
node=rclpy.create_node('release_drive_check')
state={}
for key, topic in [('truth','/ground_truth/odom'),('encoder','/ground/encoder_odom')]:
    node.create_subscription(Odometry,topic,lambda msg,k=key:state.update({k:msg}),qos_profile_sensor_data)
node.create_subscription(Twist,'/virtual/internal_drive',lambda msg:state.update(gate=msg),10)
pub=node.create_publisher(String,'/bench/scenario',10)
def wait(seconds, drive=None):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if drive:
            pub.publish(String(data=json.dumps(dict(kind='drive',linear_mps=drive[0],angular_radps=drive[1]))))
        rclpy.spin_once(node,timeout_sec=.07)
def pose():
    p=state['truth'].pose.pose
    q=p.orientation
    return p.position.x,p.position.y,math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
def angle(a,b):
    return math.atan2(math.sin(b-a),math.cos(b-a))
for _ in range(50):
    wait(1)
    if {'truth','encoder','gate'} <= state.keys():
        break
assert {'truth','encoder','gate'} <= state.keys(),state.keys()
for label,command in [('forward',(.10,0)),('reverse',(-.10,0)),('left',(0,.35)),('right',(0,-.35))]:
    before=pose()
    enc_before=state['encoder'].pose.pose.position
    wait(5,command)
    after=pose()
    enc_after=state['encoder'].pose.pose.position
    displacement=math.dist(before[:2],after[:2])
    enc_displacement=math.hypot(enc_after.x-enc_before.x,enc_after.y-enc_before.y)
    yaw=angle(before[2],after[2])
    signed_distance=(after[0]-before[0])*math.cos(before[2])+(after[1]-before[1])*math.sin(before[2])
    print(label, f'truth_m={displacement:.4f} encoder_m={enc_displacement:.4f} truth_yaw_rad={yaw:.4f}',flush=True)
    if command[0]:
        assert signed_distance*math.copysign(1,command[0]) > .003
    else:
        assert yaw*math.copysign(1,command[1]) > .01
    wait(.6)
    assert state['gate'].linear.x==0 and state['gate'].angular.z==0
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
print('timeout, duplicate, stopped before fresh command, resumed, explicit stop verified',flush=True)
node.destroy_node()
rclpy.shutdown()
PY
