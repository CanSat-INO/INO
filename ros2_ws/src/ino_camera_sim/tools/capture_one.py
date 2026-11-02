"""Save one rectified camera image for a bounded renderer check."""
import argparse
import time
import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

p=argparse.ArgumentParser();p.add_argument('output');a=p.parse_args()
rclpy.init();node=Node('camera_renderer_check');bridge=CvBridge();received=[]
def callback(m):
    cv2.imwrite(a.output,bridge.imgmsg_to_cv2(m,'bgr8'));received.append((m.width,m.height))
sub=node.create_subscription(Image,'/stereo/left/image',callback,10)
end=time.monotonic()+45
try:
    while not received and time.monotonic()<end:rclpy.spin_once(node,timeout_sec=.2)
finally:node.destroy_node();rclpy.try_shutdown()
print(received)
if not received:raise SystemExit(1)
