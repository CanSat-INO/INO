"""Wait on wall time for actual bridge data before starting a controller."""
import os
import time
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
from rosgraph_msgs.msg import Clock

if os.environ.get("ROS_DISTRO") == "lyrical":
    from gz.transport15 import Node as GzNode
    from gz.msgs.clock_pb2 import Clock as GzClock
    from gz.msgs.world_stats_pb2 import WorldStatistics
else:
    from gz.transport13 import Node as GzNode
    from gz.msgs10.clock_pb2 import Clock as GzClock
    from gz.msgs10.world_stats_pb2 import WorldStatistics

def main():
    rclpy.init();node=Node('mission_input_readiness');seen=set()
    gz_counts={'clock':0,'world_clock':0,'stats':0};gz_state={};gz=GzNode()
    gz.subscribe(GzClock,'/clock',lambda msg:gz_counts.update(clock=gz_counts['clock']+1))
    gz.subscribe(GzClock,'/world/mission_lab/clock',lambda msg:gz_counts.update(world_clock=gz_counts['world_clock']+1))
    gz.subscribe(WorldStatistics,'/world/mission_lab/stats',lambda msg:(gz_counts.update(stats=gz_counts['stats']+1),gz_state.update(paused=msg.paused)))
    subs=[node.create_subscription(cls,topic,lambda msg,key=key:seen.add(key),10) for cls,topic,key in [(Clock,'/clock','clock'),(Odometry,'/ground_truth/odom','odometry'),(Image,'/raw/left/image','camera')]]
    end=time.monotonic()+60
    while len(seen)<3 and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.1)
    node.get_logger().info('Mission input readiness: '+','.join(sorted(seen)))
    node.get_logger().info('Native Gazebo input: '+str(gz_counts)+' '+str(gz_state))
    node.destroy_node();rclpy.shutdown()
    if len(seen)<3:raise SystemExit(1)

if __name__=='__main__':main()
