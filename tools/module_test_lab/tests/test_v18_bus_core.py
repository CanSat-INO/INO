from __future__ import annotations

import csv
import io
import json
import math
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v18_bus_core import (BusConfig, SCENARIOS, validate_config, validate_packet,
                          run_bus_test, csv_text, json_text, scenario_signature)


class BusTest(unittest.TestCase):
    def test_normal(self):
        r = run_bus_test()
        self.assertEqual(r.status, 'PASS')
        self.assertGreaterEqual(r.delivered, 10)
        self.assertEqual(r.pending_ack, 0)
        self.assertEqual(r.dropped, 0)
        self.assertTrue(any(e['kind'] == 'CAM_TARGET' and e['state'] == '受信' for e in r.events))

    def test_ack_missing(self):
        r = run_bus_test('drop_drive_ack')
        self.assertEqual(r.status, 'STOPPED')
        self.assertIn('期限超過', r.reason)
        self.assertEqual(r.dropped, 1)

    def test_camera_missing(self):
        r = run_bus_test('drop_cam_target')
        self.assertEqual(r.status, 'STOPPED')
        self.assertIn('CAM', r.reason)
        self.assertFalse(any(e['kind'] == 'DRIVE_CMD' and e['detail'] == 'CAM_APPROACH' and e['state'] == '送信' for e in r.events))

    def test_duplicate_is_safe(self):
        r = run_bus_test('duplicate_cmd')
        self.assertEqual(r.status, 'PASS')
        self.assertEqual(r.duplicates, 1)
        self.assertEqual(r.pending_ack, 0)

    def test_latency_timeout(self):
        r = run_bus_test('delay_drive_ack')
        self.assertEqual(r.status, 'STOPPED')
        self.assertEqual(r.dropped, 0)
        self.assertIn('期限超過', r.reason)

    def test_old_camera_packet(self):
        r = run_bus_test('stale_cam_target')
        self.assertEqual(r.status, 'STOPPED')
        self.assertTrue(any(e['state'] == '拒否' for e in r.events))

    def test_emergency(self):
        r = run_bus_test('emergency')
        self.assertEqual(r.status, 'STOPPED')
        self.assertTrue(any(e['kind'] == 'EMERGENCY' and e['state'] == '受信' for e in r.events))
        self.assertTrue(any(e['kind'] == 'DRIVE_CMD' and e['detail'] == 'STOP' and e['time_s'] > 8 for e in r.events))

    def test_all_scenarios_are_deterministic(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                a, b = run_bus_test(scenario), run_bus_test(scenario)
                self.assertEqual(a, b)
                self.assertEqual(scenario_signature(a), scenario_signature(b))

    def test_contract_validation(self):
        with self.assertRaises(ValueError):
            validate_packet('Camera', 'Drive', 'DRIVE_CMD', 1, 0)
        with self.assertRaises(ValueError):
            validate_packet('Main', 'Drive', 'DRIVE_CMD', True, 0)
        with self.assertRaises(ValueError):
            validate_packet('Main', 'Drive', 'DRIVE_CMD', 1, math.nan)

    def test_configuration_limits(self):
        for c in (BusConfig(latency_s=0), BusConfig(ack_timeout_s=0),
                  BusConfig(target_deadline_s=float('nan')), BusConfig(max_age_s=99)):
            with self.assertRaises(ValueError):
                validate_config(c)

    def test_csv_and_json_export(self):
        r = run_bus_test()
        events = list(csv.DictReader(io.StringIO(csv_text(r))))
        self.assertEqual(len(events), len(r.events))
        self.assertEqual(json.loads(json_text(r))['schema'], 'cansat.virtual_bus.v18')
        self.assertEqual(json.loads(json_text(r))['status'], 'PASS')

    def test_no_external_hardware_imports(self):
        code = (Path(__file__).resolve().parents[1] / 'v18_bus_core.py').read_text()
        for term in ('import serial', 'import rclpy', 'import requests', 'import socket', 'import machine'):
            self.assertNotIn(term, code)


if __name__ == '__main__':
    unittest.main()
