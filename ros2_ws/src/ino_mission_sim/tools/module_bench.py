"""Provisional module exchange on a local, isolated virtual ROS domain."""
import argparse
from collections import OrderedDict
import json
import math
from pathlib import Path
import time

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock as ClockMessage
from sensor_msgs.msg import Imu
from std_msgs.msg import String
from std_srvs.srv import Trigger


ROLES = ('main', 'camera', 'drive', 'vision', 'station')
PRESETS = {
    'main': ('external', 'mock', 'mock', 'disabled', 'disabled'),
    'camera': ('mock', 'external', 'mock', 'disabled', 'disabled'),
    'drive': ('mock', 'mock', 'external', 'disabled', 'disabled'),
    'vision': ('mock', 'mock', 'disabled', 'external', 'disabled'),
    'all': ('mock', 'mock', 'mock', 'disabled', 'mock'),
    'station': ('mock', 'mock', 'disabled', 'disabled', 'mock'),
}


class Bench(Node):
    def __init__(self, modes, log, fault, manual_sensors):
        super().__init__('ino_module_bench')
        self.modes = modes
        self.log = log
        self.fault = fault
        self.counter = 0
        self.retained = OrderedDict()
        self.pending = None
        self.capture_job = None
        self.sim_stamp = None
        self.last_capture_id = 0
        self.expiries = {}
        self.deployment = 'undeployed'
        self.deployment_due = None
        self.sensors = manual_sensors.copy()
        self.events = self.create_publisher(String, '/bench/events', 20)
        self.inputs = {role: self.create_publisher(String, f'/bench/{role}/input', 20)
                       for role in ROLES if modes[role] == 'external'}
        for role in self.inputs:
            self.create_subscription(String, f'/bench/{role}/output',
                                     lambda msg, role=role: self.receive(role, msg), 20)
        if modes['main'] == 'mock':
            self.create_subscription(String, '/bench/scenario',
                                     lambda msg: self.receive('main', msg), 20)
        self.capture = self.create_client(Trigger, '/virtual/capture')
        self.motion = (self.create_publisher(Twist, '/cmd_vel', 10)
                       if modes['drive'] != 'disabled' else None)
        self.create_subscription(ClockMessage, '/clock', self.clock_update, qos_profile_sensor_data)
        self.create_subscription(Imu, '/ground/imu', self.imu, qos_profile_sensor_data)
        self.create_subscription(Odometry, '/ground/encoder_odom', self.encoder, qos_profile_sensor_data)
        self.create_timer(0.5, self.telemetry)
        self.create_timer(0.25, self.capture_tick, clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.create_timer(0.1, self.deployment_tick, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def clock_update(self, msg):
        stamp = (msg.clock.sec, msg.clock.nanosec)
        if self.sim_stamp is not None and stamp < self.sim_stamp and self.capture_job:
            capture_id, _, _ = self.capture_job
            if self.pending is not None:
                self.capture.remove_pending_request(self.pending)
                self.pending = None
            self.capture_job = None
            self.send('main', 'error', capture_id=capture_id, detail='simulation clock reset')
        self.sim_stamp = stamp

    def imu(self, msg):
        self.sensors['imu'] = {'source': 'gazebo', 'frame': msg.header.frame_id,
            'stamp_ns': msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec,
            'acceleration_mps2': [msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z],
            'angular_radps': [msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z]}

    def encoder(self, msg):
        self.sensors['encoder'] = {'source': 'gazebo_track_odometry', 'forward_mps': msg.twist.twist.linear.x,
            'stamp_ns': msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec}

    def telemetry(self):
        self.send('main', 'sensors', sensors=self.sensors.copy(), deployment=self.deployment)
        if self.modes['station'] != 'disabled':
            self.send('station', 'telemetry', sensors=self.sensors.copy())

    def send(self, role, kind, **data):
        channel = 'twelite' if role == 'station' else ('ros' if role == 'vision' else 'can')
        if kind == 'image_transfer':
            channel = 'wifi'
        payload = {'version': 1, 'role': role, 'kind': kind, 'channel': channel,
                   'wall_ns': time.time_ns(), **data}
        msg = String(data=json.dumps(payload, allow_nan=False))
        self.log.write(msg.data + '\n')
        self.events.publish(msg)
        if kind not in ("telemetry", "sensors", "drive_request"):
            print(msg.data, flush=True)
        if role in self.inputs:
            self.inputs[role].publish(msg)

    def receive(self, role, msg):
        try:
            source = '/bench/scenario' if role == 'main' and self.modes[role] == 'mock' else f'/bench/{role}/output'
            if self.count_publishers(source) != 1:
                raise ValueError('exactly one publisher is required for ' + source)
            data = json.loads(msg.data)
            if not isinstance(data, dict):
                raise ValueError('expected JSON object')
            kind = data.get('kind')
            if role == 'main' and kind == 'capture':
                self.request_capture(data.get('capture_id'))
            elif role == 'main' and kind == 'deploy':
                self.request_deployment(data)
            elif role == 'main' and kind == 'drive':
                self.request_drive(data)
            elif role == 'drive' and kind == 'motor':
                request_id = data.get('request_id')
                expiry = self.expiries.pop(request_id, 0)
                if time.monotonic() < expiry:
                    self.command(data)
                else:
                    self.send('main', 'error', detail='expired or unknown motor request')
            elif role == 'camera' and kind == 'image_retained':
                capture_id = data['capture_id']
                if type(capture_id) is not int or capture_id not in self.retained:
                    raise ValueError('unknown or released capture')
                self.send('main', 'image_retained', capture_id=capture_id)
                self.transfer(capture_id)
            elif role == 'main' and kind == 'release_capture':
                self.retained.pop(data['capture_id'], None)
            elif kind == 'status':
                self.send('station', 'module_status', module=role, detail=str(data.get('detail', '')))
            else:
                raise ValueError('unsupported operation')
        except (ValueError, TypeError, KeyError) as error:
            self.send('main', 'error', module=role, detail=str(error))

    def request_deployment(self, data):
        if self.modes['drive'] != 'mock':
            raise ValueError('logical deployment requires Mock Drive')
        if data.get('release_confirmed') is not True or data.get('landing_confirmed') is not True:
            raise ValueError('logical deployment requires confirmed release and landing fixtures')
        if self.deployment != 'undeployed':
            raise ValueError('deployment has already been requested')
        self.deployment = 'deploying'
        self.deployment_due = time.monotonic() + 0.5
        self.send('main', 'deployment', state=self.deployment, source='logical_fixture')

    def deployment_tick(self):
        if self.deployment_due is None or time.monotonic() < self.deployment_due:
            return
        self.deployment_due = None
        self.deployment = 'failed' if self.fault == 'deployment_failure' else 'deployed'
        self.send('main', 'deployment', state=self.deployment, source='logical_fixture')

    def request_drive(self, data):
        if self.motion is None:
            return
        if self.fault == 'motor_stop':
            self.motion.publish(Twist())
            self.send('main', 'error', detail='simulated motor stop')
            return
        if self.modes['drive'] == 'mock':
            self.command(data)
        elif self.modes['drive'] == 'external':
            self.counter += 1
            now = time.monotonic()
            self.expiries = {key: expiry for key, expiry in self.expiries.items() if expiry > now}
            self.expiries[self.counter] = now + 0.25
            self.send('drive', 'drive_request', request_id=self.counter,
                      linear_mps=data['linear_mps'], angular_radps=data['angular_radps'],
                      encoder=self.sensors.get('encoder'))

    def command(self, data):
        linear, angular = float(data['linear_mps']), float(data['angular_radps'])
        if not math.isfinite(linear) or not math.isfinite(angular):
            raise ValueError('nonfinite speed')
        msg = Twist()
        msg.linear.x = max(-0.2, min(0.2, linear))
        msg.angular.z = max(-0.5, min(0.5, angular))
        self.motion.publish(msg)

    def request_capture(self, capture_id):
        if self.modes['camera'] == 'disabled':
            self.send('main', 'error', detail='camera disabled')
            return
        if self.capture_job is not None:
            self.send('main', 'error', detail='camera busy or unavailable')
            return
        if len(self.retained) >= 8:
            self.send('main', 'error', detail='capture buffer full')
            return
        if capture_id is None and self.modes['main'] == 'mock':
            capture_id = self.last_capture_id + 1
        if type(capture_id) is not int or not self.last_capture_id < capture_id <= 2**53 - 1:
            raise ValueError('Main must supply an increasing positive capture ID')
        self.last_capture_id = capture_id
        self.send('camera', 'capture_request', capture_id=capture_id)
        self.capture_job = (capture_id, time.monotonic() + 15, self.sim_stamp)

    def capture_tick(self):
        if self.capture_job is None:
            return
        capture_id, deadline, _ = self.capture_job
        if time.monotonic() >= deadline:
            if self.pending is not None:
                self.capture.remove_pending_request(self.pending)
            self.pending = None
            self.capture_job = None
            self.send('main', 'error', capture_id=capture_id, detail='snapshot timeout')
        elif self.pending is None and self.capture.service_is_ready():
            self.pending = self.capture.call_async(Trigger.Request())
            self.pending.add_done_callback(lambda future: self.capture_result(capture_id, future))

    def capture_result(self, capture_id, future):
        if future is not self.pending:
            return
        self.pending = None
        try:
            response = future.result()
            if not response.success:
                return
            metadata = json.loads(response.message)
            stamp = tuple(map(int, metadata['capture_id'].split('_')))
            requested_stamp = self.capture_job[2]
            if requested_stamp is not None and stamp <= requested_stamp:
                return
            self.capture_job = None
            folder = Path(metadata['path'])
            files = {side: str(folder / f'{side}.png') for side in ('left', 'right')}
            if self.fault == 'camera_right_missing' or not all(Path(file).is_file() for file in files.values()):
                self.send('main', 'error', capture_id=capture_id, detail='incomplete stereo pair')
                return
            self.retained[capture_id] = files
            self.send('main', 'capture_complete', capture_id=capture_id, snapshot_id=metadata['capture_id'])
            self.send('camera', 'capture_input', capture_id=capture_id,
                      snapshot_id=metadata['capture_id'], images=files)
            if self.modes['camera'] == 'mock':
                self.send('main', 'image_retained', capture_id=capture_id)
                self.transfer(capture_id)
        except (ValueError, OSError, RuntimeError) as error:
            self.send('main', 'error', capture_id=capture_id, detail=str(error))

    def transfer(self, capture_id):
        if self.fault == 'wifi_down':
            self.send('main', 'error', capture_id=capture_id, detail='simulated Wi-Fi disconnect')
        elif self.modes['station'] != 'disabled':
            self.send('station', 'image_transfer', capture_id=capture_id,
                      images=self.retained[capture_id])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=PRESETS, default='all')
    parser.add_argument('--set', action='append', default=[], metavar='ROLE=MODE')
    parser.add_argument('--fault', choices=('none', 'motor_stop', 'wifi_down', 'camera_right_missing', 'deployment_failure'), default='none')
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--manual-sensors', type=Path)
    args = parser.parse_args()
    modes = dict(zip(ROLES, PRESETS[args.preset]))
    for option in args.set:
        role, _, mode = option.partition('=')
        if role not in modes or mode not in ('mock', 'external', 'disabled'):
            parser.error('expected ROLE=mock|external|disabled')
        modes[role] = mode
    manual = {}
    if args.manual_sensors:
        data = json.loads(args.manual_sensors.read_text())
        for name, spec in data.items():
            if name not in ('gnss', 'magnetic_field', 'pressure', 'temperature', 'battery_voltage', 'mechanism'):
                parser.error(f'unsupported manual sensor {name}')
            if not isinstance(spec, dict) or not {'value', 'unit', 'frame', 'valid'} <= spec.keys() or type(spec['valid']) is not bool:
                parser.error(f'{name} requires value, unit, frame and boolean valid')
            manual[name] = {**spec, 'source': 'manual_fixture', 'stamp_ns': None}
        json.dumps(manual, allow_nan=False)
    rclpy.init()
    with args.log.open('x', buffering=1) as log:
        node = Bench(modes, log, args.fault, manual)
        node.send('station', 'configuration', modes=modes, fault=args.fault)
        try:
            rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        finally:
            node.destroy_node()
            rclpy.try_shutdown()


if __name__ == '__main__':
    main()
