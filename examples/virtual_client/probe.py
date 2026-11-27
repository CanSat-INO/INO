#!/usr/bin/env python3
"""Check ROS input and request one synchronized snapshot."""
import argparse
from collections import Counter
import math
import time

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.qos import QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import CameraInfo, Image, Imu
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--drive', action='store_true', help='Send a short virtual-only drive command')
    parser.add_argument('--replay', action='store_true', help='Check only recorded sensor topics')
    args = parser.parse_args(rclpy.utilities.remove_ros_args()[1:])
    if args.replay and args.drive:
        parser.error('--replay cannot be combined with --drive')
    rclpy.init()
    node = rclpy.create_node('ino_virtual_probe')
    received = {}
    counts = Counter()
    replay_frames = {}

    def receive(name, message):
        received[name] = message
        counts[name] += 1
        if args.replay and name.startswith('/raw/'):
            if isinstance(message, CameraInfo) and not (message.k[0] > 0 and message.k[4] > 0):
                return
            if isinstance(message, Image) and not message.data:
                return
            stamp = message.header.stamp
            key = (stamp.sec, stamp.nanosec)
            replay_frames.setdefault(key, {})[name] = (message.width, message.height, message.header.frame_id)
            if len(replay_frames) > 256:
                replay_frames.pop(next(iter(replay_frames)))
    def synchronized_frames():
        for stamp, frames in replay_frames.items():
            if len(frames) != 4:
                continue
            if all(frames[f'/raw/{side}/image'] == frames[f'/raw/{side}/camera_info']
                   for side in ('left', 'right')):
                yield stamp
    topics = {'/clock': Clock, '/ground/imu': Imu, '/ground/encoder_odom': Odometry, '/odom': Odometry}
    if args.replay:
        topics = {name: topics[name] for name in ('/clock', '/ground/imu')}
    for side in ('left', 'right'):
        topics[f'/raw/{side}/image'] = Image
        topics[f'/raw/{side}/camera_info'] = CameraInfo
    for topic, msg_type in topics.items():
        node.create_subscription(msg_type, topic, lambda msg, name=topic: receive(name, msg),
                                 QoSProfile(depth=5) if args.replay and msg_type in (Image, CameraInfo) else qos_profile_sensor_data)
    buffer = Buffer()
    listener = TransformListener(buffer, node)
    capture = None if args.replay else node.create_client(Trigger, '/virtual/capture')
    command = node.create_publisher(Twist, '/cmd_vel', 10) if args.drive else None
    start = time.monotonic()
    matched = set()
    try:
        while time.monotonic() - start < (90 if args.replay else 40):
            rclpy.spin_once(node, timeout_sec=0.1)
            if args.replay:
                matched = set(synchronized_frames())
                if len(matched) < 3:
                    continue
            if (topics.keys() <= received.keys() and (args.replay or (capture.service_is_ready()
                    and buffer.can_transform('odom', 'left_raw_optical', Time())))):
                break
        else:
            raise RuntimeError(f'Incomplete input: counts={dict(counts)}, synchronized stereo+CameraInfo sets={len(matched)}')
        if node.get_clock().now().nanoseconds == 0 or not node.get_parameter('use_sim_time').value:
            raise RuntimeError('Enable use_sim_time with --ros-args -p use_sim_time:=true')
        if args.replay:
            for side in ('left', 'right'):
                image = received[f'/raw/{side}/image']
                info = received[f'/raw/{side}/camera_info']
                if (image.width, image.height) != (info.width, info.height):
                    raise RuntimeError(f'{side} CameraInfo does not match image dimensions')
                if not image.data or not (image.header.stamp.sec or image.header.stamp.nanosec):
                    raise RuntimeError(f'{side} image or stamp is missing')
            print(f'Replay verified: {dict(counts)}, synchronized stereo+CameraInfo sets={len(matched)}', flush=True)
            return
        capture_deadline = time.monotonic() + 15
        while time.monotonic() < capture_deadline:
            future = capture.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(node, future, timeout_sec=2)
            if future.done() and future.result().success:
                print(f'capture: {future.result().message}', flush=True)
                break
            time.sleep(0.2)
            rclpy.spin_once(node, timeout_sec=0.15)
        else:
            raise RuntimeError('No synchronized snapshot received')
        if command:
            initial = received['/odom'].pose.pose.position
            twist = Twist()
            twist.linear.x = 0.06
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                command.publish(twist)
                rclpy.spin_once(node, timeout_sec=0.05)
            final = received['/odom'].pose.pose.position
            displacement = math.hypot(final.x - initial.x, final.y - initial.y)
            if displacement < 0.005:
                raise RuntimeError('Virtual drive did not produce encoder odometry')
            print(f'encoder displacement: {displacement:.3f} m', flush=True)
        print('ROS input, TF, clock and capture verified', flush=True)
    finally:
        if command:
            for _ in range(3):
                command.publish(Twist())
                rclpy.spin_once(node, timeout_sec=0.05)
        listener.unregister()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
