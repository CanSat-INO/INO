"""v11 common format tests: no Qt, ROS2, network or hardware required."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from module_network import simulate
from simulation_common import (
    CommonFormatError, SCHEMA, RUN_SCHEMA, default_config, validate_config,
    config_json, parse_config, load_config, save_config, make_run, run_json, run_csv,
)


class CommonFormatTests(unittest.TestCase):
    def test_default_roundtrip(self):
        cfg = default_config()
        self.assertEqual(parse_config(config_json(cfg)),cfg)
        self.assertEqual(cfg['schema'],SCHEMA)

    def test_default_is_independent(self):
        a = default_config(); a['robot']['name'] = 'edited'
        self.assertEqual(default_config()['robot']['name'],'INO-demo')

    def test_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'config.json'
            save_config(path,default_config())
            self.assertEqual(load_config(path),default_config())

    def test_reject_schema(self):
        cfg = default_config(); cfg['schema']='unknown'
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_future_version(self):
        cfg = default_config(); cfg['version']=2
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_unknown_key(self):
        cfg = default_config(); cfg['secret']='x'
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_missing_key(self):
        cfg = default_config(); del cfg['robot']['name']
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_negative_mass(self):
        cfg = default_config(); cfg['robot']['mass_kg']=-1
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_bool_mass(self):
        cfg = default_config(); cfg['robot']['mass_kg']=True
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_nan(self):
        cfg = default_config(); cfg['robot']['mass_kg']=float('nan')
        with self.assertRaises(CommonFormatError): validate_config(cfg)
        with self.assertRaises(CommonFormatError): parse_config(config_json(default_config()).replace('0.8','NaN'))

    def test_reject_invalid_quaternion(self):
        cfg = default_config(); cfg['initial_state']['orientation_xyzw']=[0,0,0,0]
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_unknown_scenario(self):
        cfg = default_config(); cfg['scenario']['key']='not_real'
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_non_string_scenario(self):
        cfg = default_config(); cfg['scenario']['key']=['normal']
        with self.assertRaises(CommonFormatError): validate_config(cfg)

    def test_reject_invalid_json(self):
        with self.assertRaises(CommonFormatError): parse_config('{')

    def test_reject_large_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'huge.json'; path.write_bytes(b' ' * 1000001)
            with self.assertRaises(CommonFormatError): load_config(path)

    def test_result_is_honest_about_physics(self):
        run = make_run(default_config(),simulate('normal'),created_at='2026-01-01T00:00:00Z')
        self.assertEqual(run['schema'],RUN_SCHEMA)
        self.assertFalse(run['physical_parameters_applied'])
        self.assertTrue(run['samples'])
        self.assertTrue(all(x['position_m'] is None and x['orientation_xyzw'] is None
                            and x['velocity_mps'] is None for x in run['samples']))
        self.assertEqual(run['source'],'ino.virtual_can.v8')

    def test_result_events_preserved(self):
        original=simulate('drop_drive_cmd')
        cfg=default_config(); cfg['scenario']['key']='drop_drive_cmd'
        run=make_run(cfg,original)
        self.assertEqual([x['time_s'] for x in run['samples']], [e.time_ms/1000 for e in original.events])
        self.assertEqual([x['event'] for x in run['samples']], [e.event for e in original.events])
        self.assertEqual(run['result']['timeout_count'],original.timeout_count)

    def test_result_mismatch_rejected(self):
        with self.assertRaises(CommonFormatError): make_run(default_config(),simulate('drop_drive_cmd'))

    def test_json_and_csv_export(self):
        run=make_run(default_config(),simulate('normal'))
        self.assertEqual(json.loads(run_json(run))['result']['evaluation'],'成功')
        rows=list(csv.DictReader(io.StringIO(run_csv(run))))
        self.assertEqual(len(rows),len(run['samples']))
        self.assertTrue(all(x['position_x_m']=='' for x in rows))
        self.assertTrue(all(x['orientation_w']=='' for x in rows))

    def test_all_scenarios(self):
        from module_network import SCENARIOS
        for scenario in SCENARIOS:
            cfg=default_config(); cfg['scenario']['key']=scenario.key
            run=make_run(cfg,simulate(scenario.key))
            self.assertEqual(run['config']['scenario']['key'],scenario.key)

    def test_config_is_copied(self):
        cfg=default_config()
        run=make_run(cfg,simulate('normal'))
        cfg['robot']['name']='changed'
        self.assertEqual(run['config']['robot']['name'],'INO-demo')


if __name__=='__main__': unittest.main()
