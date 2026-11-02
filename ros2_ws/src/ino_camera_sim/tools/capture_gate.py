"""Select actual Gazebo frames; retain acquisition timestamps, including skew."""
import argparse
import math
import copy
import random
import cv2
from cv_bridge import CvBridge
from std_msgs.msg import String
from design_config import load
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo
from rtabmap_msgs.msg import RGBDImage
from geometry_msgs.msg import Twist

class CaptureGate(Node):
    def __init__(self,cfg=None):
        super().__init__('capture_gate')
        self.declare_parameter('mode', (cfg or {'capture':{'mode':'continuous'}})['capture']['mode'])
        self.declare_parameter('settle_time', cfg['capture']['settle_s'] if cfg else .5)
        self.declare_parameter('period', cfg['capture']['period_s'] if cfg else 1.0)
        self.declare_parameter('skew', cfg['capture']['skew_s'] if cfg else .1)
        self.mode = self.get_parameter('mode').value
        fps=cfg['camera']['fps'] if cfg else 10
        self.quantized_skew=math.ceil(self.get_parameter('skew').value*fps-1e-9)/fps
        if self.mode not in ('continuous', 'stop', 'sequential'):
            raise ValueError('mode must be continuous, stop, or sequential')
        self.options = cfg['capture'] if cfg else {'acquisition_s':0.,'transmission_s':0.,'drop_probability':0.,'jpeg_quality':100,'seed':27}
        self.rng = random.Random(self.options['seed'])
        self.bridge = CvBridge()
        self.queue = []
        self.dropped = 0
        self.status = self.create_publisher(String,'/capture/status',10)
        self.timer = self.create_timer(.02,self.flush)
        self.frame_tolerance = .5/(cfg['camera']['fps'] if cfg else 10)
        self.frames = {}
        self.pending = None
        # The generated robot starts at rest. Capture without requiring a keyboard command.
        self.stopped_at = 0.0
        self.last_pair = -1e9
        self.pair_pub = self.create_publisher(RGBDImage, '/capture/rgbd_image', 10)
        self.pub = {}
        self.subs = []
        for side in ('left', 'right'):
            for kind, cls in (('image', Image), ('camera_info', CameraInfo)):
                key = (side, kind)
                self.pub[key] = self.create_publisher(cls, f'/capture/{side}/{kind}', 10)
                self.subs.append(self.create_subscription(cls, f'/stereo/{side}/{kind}', lambda msg,k=key:self.receive(k,msg), 10))
        self.subs.append(self.create_subscription(Twist, '/cmd_vel', self.command, 10))

    def command(self, msg):
        moving = any(abs(x)>1e-5 for x in (msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z))
        if moving:
            self.stopped_at = None
            self.pending = None
        elif self.stopped_at is None:
            self.stopped_at = self.get_clock().now().nanoseconds/1e9

    def receive(self, key, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec/1e9
        frame = self.frames.setdefault(stamp,{})
        frame[key] = msg
        for old in sorted(self.frames)[:-12]:
            del self.frames[old]
        if len(frame) != 4:
            return
        del self.frames[stamp]
        if self.mode == 'continuous':
            self.emit(frame)
            return
        if self.stopped_at is None or stamp-self.stopped_at<self.get_parameter('settle_time').value:
            return
        if self.pending is not None:
            if stamp-self.pending[0] > self.quantized_skew + self.frame_tolerance:
                self.pending = (stamp,frame)
                return
            if stamp-self.pending[0] >= self.quantized_skew-1e-6:
                pair = dict(self.pending[1])
                for kind in ('image','camera_info'):
                    pair[('right',kind)] = frame[('right',kind)]
                self.emit(pair)
                self.last_pair = stamp
                self.pending = None
            return
        if stamp-self.last_pair < self.get_parameter('period').value:
            return
        if self.mode == 'sequential' and self.quantized_skew>0:
            self.pending = (stamp,frame)
        else:
            self.emit(frame)
            self.last_pair = stamp

    def emit(self, frame):
        if self.rng.random()<self.options['drop_probability']:
            self.dropped += 1
            return
        if len(self.queue)>=64:
            self.dropped += 1
            return
        due = self.get_clock().now().nanoseconds/1e9+self.options['acquisition_s']+self.options['transmission_s']
        self.queue.append((due,frame))

    def flush(self):
        now=self.get_clock().now().nanoseconds/1e9
        while self.queue and self.queue[0][0]<=now:
            due,frame=self.queue.pop(0)
            self.publish_pair(frame)

    def publish_pair(self, frame):
        frame=copy.deepcopy(frame)
        quality=self.options['jpeg_quality']
        jpeg_bytes=0
        if quality<100:
            for side in ('left','right'):
                msg=frame[(side,'image')]
                image=self.bridge.imgmsg_to_cv2(msg,'bgr8')
                ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,quality])
                if not ok:raise RuntimeError('JPEG encoding failed')
                jpeg_bytes+=len(encoded)
                decoded=cv2.imdecode(encoded,cv2.IMREAD_COLOR)
                out=self.bridge.cv2_to_imgmsg(cv2.cvtColor(decoded,cv2.COLOR_BGR2RGB),'rgb8')
                out.header=msg.header
                frame[(side,'image')]=out
        pair = RGBDImage()
        # RTAB-Map stamps stereo odometry with the later acquisition.
        # Keep individual image timestamps intact; the container marks pair completion.
        pair.header = frame[('right','image')].header
        pair.rgb = frame[('left','image')]
        pair.depth = frame[('right','image')]
        pair.rgb_camera_info = frame[('left','camera_info')]
        pair.depth_camera_info = frame[('right','camera_info')]
        self.pair_pub.publish(pair)
        import json
        self.status.publish(String(data=json.dumps({'jpeg_bytes':jpeg_bytes,'dropped_pairs':self.dropped,'published_sim_time':self.get_clock().now().nanoseconds/1e9})))
        for key,msg in frame.items():
            self.pub[key].publish(msg)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config');args,ros=parser.parse_known_args()
    rclpy.init(args=ros)
    node = CaptureGate(load(args.config) if args.config else None)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == '__main__':
    main()
