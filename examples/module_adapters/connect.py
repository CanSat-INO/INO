"""Run an explicitly selected native C++ adapter for an EXTERNAL bench role."""
import argparse
import json
from pathlib import Path
import subprocess

import rclpy
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import String


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role', choices=('main', 'camera', 'drive'))
    parser.add_argument('binary', type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    rclpy.init()
    node = rclpy.create_node(f'bench_adapter_{args.role}')
    output = node.create_publisher(String, f'/bench/{args.role}/output', 20)
    main_requested = False

    def handle(msg):
        nonlocal main_requested
        try:
            data = json.loads(msg.data)
            if args.role == 'main' and data['kind'] == 'sensors' and not main_requested:
                if 'imu' not in data['sensors']:
                    return
                request = json.dumps(data['sensors']['imu'])
            elif args.role == 'camera' and data['kind'] == 'capture_input':
                request = f"{data['images']['left']}\n{data['images']['right']}"
            elif args.role == 'drive' and data['kind'] == 'drive_request':
                request = f"{data['linear_mps']} {data['angular_radps']}"
            else:
                return
            result = subprocess.run([str(binary), args.role], input=request + '\n',
                                    text=True, capture_output=True, check=True, timeout=0.2)
            reply = result.stdout.strip()
            if args.role == 'main' and reply == 'capture':
                main_requested = True
                result = {'kind': 'capture', 'capture_id': 1}
            elif args.role == 'camera' and reply == 'retain':
                result = {'kind': 'image_retained', 'capture_id': data['capture_id']}
            elif args.role == 'drive':
                forward, turn = map(float, reply.split())
                result = {'kind': 'motor', 'request_id': data['request_id'],
                          'linear_mps': forward, 'angular_radps': turn}
            else:
                raise ValueError('adapter returned an unsupported action')
            output.publish(String(data=json.dumps(result, allow_nan=False)))
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            node.get_logger().error(str(error))

    node.create_subscription(String, f'/bench/{args.role}/input', handle, 20)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
