"""v12 experiment-batch regression tests; runnable without Qt, ROS2, or external IO."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from experiment_management import (
    ExperimentError, MAX_CASES, BATCH_SCHEMA, PLAN_SCHEMA, new_plan, make_case,
    validate_plan, plan_json, parse_plan, default_scenario_plan, run_plan,
    batch_csv, batch_json, parse_batch, save_history, load_history, list_history,
)
from simulation_common import default_config
from module_network import SCENARIOS, simulate


class ExperimentManagementTests(unittest.TestCase):
    def example(self):
        plan = new_plan('走行指令と応答の比較')
        a = default_config()
        b = default_config()
        b['robot']['wheel_diameter_m'] = 0.09
        b['scenario']['key'] = 'drop_drive_ack'
        plan['cases'] = [make_case(a,'正常 / 60 mm'),make_case(b,'Drive ACK欠落 / 90 mm')]
        return plan

    def test_make_plan_roundtrip(self):
        p = self.example()
        self.assertEqual(parse_plan(plan_json(p)),validate_plan(p))
        self.assertEqual(p['schema'],PLAN_SCHEMA)

    def test_plan_copy_is_independent(self):
        p = self.example(); original = p['cases'][0]['config']['robot']['mass_kg']
        validated = validate_plan(p)
        validated['cases'][0]['config']['robot']['mass_kg']=22
        self.assertEqual(p['cases'][0]['config']['robot']['mass_kg'],original)

    def test_all_scenarios(self):
        p = default_scenario_plan()
        self.assertEqual(len(p['cases']),len(SCENARIOS))
        self.assertEqual([x['config']['scenario']['key'] for x in p['cases']],
                         [x.key for x in SCENARIOS])

    def test_empty_plan_cannot_run(self):
        with self.assertRaises(ExperimentError): run_plan(new_plan())

    def test_invalid_limits(self):
        p=default_scenario_plan()
        p['cases'] = p['cases'] * 6
        self.assertGreater(len(p['cases']),MAX_CASES)
        with self.assertRaises(ExperimentError): validate_plan(p)

    def test_bad_config_rejected(self):
        p=self.example()
        p['cases'][1]['config']['robot']['mass_kg']=-1
        with self.assertRaises(ExperimentError): validate_plan(p)

    def test_bad_schema_version_labels(self):
        for change in [lambda p: p.update(version=True),
                       lambda p: p.update(schema='wrong'),
                       lambda p: p.update(name='\n'),
                       lambda p: p['cases'][0].update(label='\n'),
                       lambda p: p.update(hidden='foo')]:
            p=self.example(); change(p)
            with self.assertRaises(ExperimentError): validate_plan(p)

    def test_json_invalid_and_large(self):
        for raw in ['{', '{"foo":NaN}', ' ' * 5_000_001]:
            with self.assertRaises(ExperimentError): parse_plan(raw)

    def test_deterministic_results_and_scenario_differences(self):
        p=self.example()
        batch=run_plan(p,created_at='2026-10-27T00:00:00+00:00',batch_id='f'*32)
        self.assertEqual(batch['schema'],BATCH_SCHEMA)
        self.assertEqual(len(batch['outcomes']),2)
        self.assertEqual(batch['outcomes'][0]['summary']['evaluation'],'成功')
        self.assertEqual(batch['outcomes'][1]['summary']['evaluation'],'失敗')
        self.assertFalse(batch['physical_parameters_applied'])
        self.assertEqual(batch['engine'],'ino.virtual_can.v8')
        self.assertTrue(all(not x['run']['physical_parameters_applied'] for x in batch['outcomes']))
        self.assertTrue(all(all(z['position_m'] is None for z in x['run']['samples'])
                            for x in batch['outcomes']))

    def test_physical_parameters_do_not_change_evaluation(self):
        p=self.example()
        p['cases'][1]['config']['scenario']['key']='normal'
        a=run_plan(p)
        s1,s2=[o['summary'] for o in a['outcomes']]
        self.assertEqual(s1,s2)
        self.assertEqual([e['event'] for e in a['outcomes'][0]['run']['samples']],
                         [e['event'] for e in a['outcomes'][1]['run']['samples']])

    def test_csv_export(self):
        batch=run_plan(self.example())
        rows=list(csv.DictReader(io.StringIO(batch_csv(batch))))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['wheel_diameter_m'],'0.06')
        self.assertEqual(rows[1]['wheel_diameter_m'],'0.09')
        self.assertEqual(rows[0]['physical_parameters_applied'],'False')
        self.assertEqual(rows[1]['evaluation'],'失敗')

    def test_json_roundtrip(self):
        batch=run_plan(self.example())
        self.assertEqual(parse_batch(batch_json(batch)),batch)

    def test_modified_batch_detected(self):
        batch=run_plan(self.example())
        batch['outcomes'][0]['summary']['event_count']=999
        with self.assertRaises(ExperimentError): batch_json(batch)

    def test_bad_json_batch_rejected(self):
        batch=run_plan(self.example())
        payload=json.loads(batch_json(batch))
        payload['physical_parameters_applied']=True
        with self.assertRaises(ExperimentError): parse_batch(json.dumps(payload))

    def test_save_load_history_and_no_overwrite(self):
        batch=run_plan(self.example())
        with tempfile.TemporaryDirectory() as directory:
            path=save_history(batch,directory)
            self.assertEqual(path.name,batch['id']+'.json')
            self.assertEqual(load_history(batch['id'],directory),batch)
            with self.assertRaises(FileExistsError): save_history(batch,directory)
            entries=list_history(directory)
            self.assertEqual(len(entries),1)
            self.assertEqual(entries[0]['count'],2)
            self.assertEqual(entries[0]['success'],1)
            self.assertEqual(entries[0]['failure'],1)

    def test_history_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ['../target', 'f'*31, '/etc/passwd', 'a'*33]:
                with self.assertRaises(ExperimentError): load_history(path,directory)

    def test_bad_history_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'a'*32+'.json').write_text('not json')
            self.assertEqual(list_history(directory),[])

    def test_all_8_cases_are_real_simulation_outputs(self):
        result=run_plan(default_scenario_plan())
        for item in result['outcomes']:
            direct=simulate(item['scenario_key'])
            self.assertEqual(item['summary']['evaluation'],direct.evaluation)
            self.assertEqual(item['summary']['loss_count'],direct.loss_count)
            self.assertEqual(item['summary']['timeout_count'],direct.timeout_count)
            self.assertEqual(item['summary']['event_count'],len(direct.events))


if __name__=='__main__': unittest.main()
