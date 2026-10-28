"""Pure-Python simulation tests; no GUI/hardware dependencies."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
import sys
import unittest
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v17_phase_core import (MODES, SCENARIOS, PhaseConfig, configuration,
                            run_phase_test, csv_text, result_document, save_csv, save_json)


class PhaseChecks(unittest.TestCase):
    def test_normal_full(self):
        result = run_phase_test('full')
        self.assertEqual(result.status, 'PASS')
        self.assertEqual([t['phase'] for t in result.transitions],
                         ['LANDING_WAIT', 'GNSS_WAIT', 'GPS_GUIDANCE',
                          'CAM_SEARCH', 'CAM_APPROACH', 'DONE'])
        self.assertGreater(result.duration_s, 10)

    def test_stage_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                result = run_phase_test(mode)
                self.assertEqual(result.status, 'PASS')
                self.assertEqual(result.transitions[-1]['phase'], 'DONE')

    def test_landing_failure(self):
        result = run_phase_test('full', 'landing_rejected')
        self.assertEqual(result.status, 'STOPPED')
        self.assertEqual([x['phase'] for x in result.transitions],
                         ['LANDING_WAIT', 'STOPPED'])

    def test_gyro_failure(self):
        conf = configuration('landing', 'normal', landing_gyro_dps=5.1)
        self.assertEqual(run_phase_test('landing', conf=conf).status, 'STOPPED')

    def test_gyro_boundary(self):
        conf = configuration('landing', 'normal', landing_gyro_dps=5)
        self.assertEqual(run_phase_test('landing', conf=conf).status, 'PASS')

    def test_stable_boundary(self):
        conf = configuration('landing', 'normal', stable_ms=600, landing_impact_mps2=15)
        self.assertEqual(run_phase_test('landing', conf=conf).status, 'PASS')

    def test_gnss_timeout(self):
        r = run_phase_test('full', 'gnss_timeout')
        self.assertEqual(r.status, 'STOPPED')
        self.assertIn('GNSS', r.reason)
        self.assertNotIn('CAM_APPROACH', [t['phase'] for t in r.transitions])

    def test_gnss_direct(self):
        self.assertEqual(run_phase_test('gnss', 'gnss_timeout').status, 'STOPPED')
        self.assertEqual(run_phase_test('gnss', 'normal').status, 'PASS')

    def test_camera_missing(self):
        r = run_phase_test('full', 'camera_missing')
        self.assertEqual(r.status, 'STOPPED')
        self.assertEqual(r.rows[-1]['target_visible'], 0)

    def test_obstacle_and_emergency(self):
        for scenario in ('obstacle', 'emergency'):
            with self.subTest(scenario=scenario):
                r = run_phase_test('full', scenario)
                self.assertEqual(r.status, 'STOPPED')
                self.assertEqual(r.rows[-1]['command'], '停止')

    def test_zero_speed_rejected(self):
        with self.assertRaises(ValueError):
            configuration('full', 'normal', gps_speed_mps=0)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            run_phase_test('full', conf=PhaseConfig(cam_speed_mps=math.nan))

    def test_unknown_mode_rejected(self):
        with self.assertRaises(ValueError):
            run_phase_test('not-available')

    def test_deterministic_result(self):
        self.assertEqual(result_document(run_phase_test('full')),
                         result_document(run_phase_test('full')))

    def test_ending_time_bound(self):
        conf = configuration('camera', 'camera_missing', max_time_s=5)
        result = run_phase_test('camera', 'camera_missing', conf)
        self.assertLessEqual(result.duration_s, 5)
        self.assertEqual(result.status, 'TIMEOUT')
        self.assertEqual(result.rows[-1]['phase'], 'STOPPED')

    def test_csv_roundtrip(self):
        r = run_phase_test('gps')
        reader = csv.DictReader(io.StringIO(csv_text(r)))
        rows = list(reader)
        self.assertEqual(len(rows), len(r.rows))
        self.assertIn('phase_ja', reader.fieldnames)

    def test_exports(self):
        r = run_phase_test('full')
        with TemporaryDirectory() as folder:
            csv_path = Path(folder) / 'r.csv'
            json_path = Path(folder) / 'r.json'
            save_csv(r, csv_path)
            save_json(r, json_path)
            self.assertTrue(csv_path.read_bytes().startswith(b'\xef\xbb\xbf'))
            data = json.loads(json_path.read_text(encoding='utf-8'))
            self.assertTrue(data['simulation_only'])
            self.assertEqual(data['status'], 'PASS')
            self.assertEqual(len(data['samples']), len(r.rows))
            self.assertEqual(len(data['config_sha256']), 64)

    def test_no_external_dependencies(self):
        import v17_phase_core
        source = Path(v17_phase_core.__file__).read_text(encoding='utf-8')
        self.assertNotIn('import rclpy', source)
        self.assertNotIn('import serial', source)
        self.assertNotIn('import PySide6', source)


if __name__ == '__main__':
    unittest.main()
