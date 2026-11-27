"""Provisional stereo snapshot service for the virtual bench."""
import argparse
from collections import OrderedDict
import json
import math
import tempfile
import time
from pathlib import Path

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import Twist
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.impl.implementation_singleton import rclpy_implementation
from rclpy.executors import ExternalShutdownException
from rclpy.utilities import remove_ros_args
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.serialization import serialize_message
from rosgraph_msgs.msg import Clock as ClockMessage
from sensor_msgs.msg import CameraInfo, Image
from std_srvs.srv import Trigger


class VirtualIO(Node):
    def __init__(self, folder, drive):
        super().__init__('virtual_io')
        self.folder = folder
        self.frames = OrderedDict()
        self.converter = CvBridge()
        self.previous_stamp = None
        self.sim_stamp = None
        self.capture_epoch = 0
        self.last_command_time = float('-inf')
        self.create_subscription(ClockMessage, '/clock', self.sim_clock, qos_profile_sensor_data)
        for side in ('left', 'right'):
            for kind, message_type in [('image', Image), ('camera_info', CameraInfo)]:
                key = (side, kind)
                self.create_subscription(message_type, f'/raw/{side}/{kind}',
                                         lambda msg, key=key: self.receive_frame(key, msg),
                                         qos_profile_sensor_data)
        self.create_service(Trigger, '/virtual/capture', self.capture)
        if drive:
            self.command_topic = self.resolve_topic_name('/cmd_vel')
            self.drive_output = self.create_publisher(Twist, '/virtual/internal_drive', 10)
            self.latest_command = Twist()
            self.create_subscription(Twist, '/cmd_vel', self.receive_command, 10)
            self.create_timer(0.05, self.forward_command, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def sim_clock(self, message):
        stamp = (message.clock.sec, message.clock.nanosec)
        if self.sim_stamp is not None and stamp < self.sim_stamp:
            self.last_command_time = float('-inf')
            self.frames.clear()
            self.previous_stamp = None
            self.capture_epoch += 1
        self.sim_stamp = stamp

    def receive_command(self, message):
        if self.count_publishers(self.command_topic) != 1:
            self.last_command_time = float('-inf')
            return
        self.last_command_time = time.monotonic()
        command = Twist()
        if math.isfinite(message.linear.x) and math.isfinite(message.angular.z):
            command.linear.x = max(-0.2, min(0.2, message.linear.x))
            command.angular.z = max(-0.5, min(0.5, message.angular.z))
        self.latest_command = command

    def forward_command(self):
        single_source = self.count_publishers(self.command_topic) == 1
        if not single_source:
            self.last_command_time = float('-inf')
        fresh = time.monotonic() - self.last_command_time < 0.35
        self.drive_output.publish(self.latest_command if single_source and fresh else Twist())

    def receive_frame(self, key, message):
        stamp = message.header.stamp
        pair = self.frames.setdefault((stamp.sec, stamp.nanosec), {})
        pair[key] = message
        while len(self.frames) > 32:
            self.frames.popitem(last=False)

    def capture(self, request, response):
        try:
            now = self.get_clock().now().nanoseconds
            ready = [stamp for stamp, pair in self.frames.items() if len(pair) == 4
                     and (self.previous_stamp is None or stamp > self.previous_stamp)
                     and 0 <= now - (stamp[0] * 10**9 + stamp[1]) <= 10**9]
            if not ready:
                response.message = 'No fresh synchronized stereo pair'
                return response
            sec, nsec = max(ready)
            pair = self.frames[sec, nsec]
            images = [pair[side, 'image'] for side in ('left', 'right')]
            infos = [pair[side, 'camera_info'] for side in ('left', 'right')]
            capture_id = f'{sec}_{nsec:09d}'
            folder_name = f'reset-{self.capture_epoch}-{capture_id}' if self.capture_epoch else capture_id
            folder = self.folder / folder_name
            with tempfile.TemporaryDirectory(dir=self.folder) as staging:
                staged = Path(staging) / 'capture'
                staged.mkdir()
                for side, image, info in zip(('left', 'right'), images, infos):
                    if not cv2.imwrite(str(staged / f'{side}.png'), self.converter.imgmsg_to_cv2(image, 'bgr8')):
                        raise OSError(f'Could not save {side} image')
                    (staged / f'{side}.camera_info.cdr').write_bytes(serialize_message(info))
                (staged / 'capture.json').write_text(json.dumps({'capture_id': capture_id,
                    'epoch': self.capture_epoch, 'stamp': {'sec': sec, 'nanosec': nsec}}, indent=2))
                staged.rename(folder)
            self.previous_stamp = (sec, nsec)
            response.success = True
            response.message = json.dumps({'capture_id': capture_id, 'path': str(folder)})
        except (OSError, ValueError, RuntimeError, cv2.error) as error:
            response.message = str(error)
        return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--drive', action='store_true')
    args = parser.parse_args(remove_ros_args()[1:])
    rclpy.init()
    node = VirtualIO(args.out, args.drive)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except rclpy_implementation.RCLError:
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
