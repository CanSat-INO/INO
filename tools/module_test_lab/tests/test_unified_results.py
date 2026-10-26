"""v9 regression tests: shared ledger format + preservation of original event logs."""
from __future__ import annotations
import csv
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import records
from dashboard_data import summary, module_summary
from module_network import simulate
from module_fault_analysis import analyze_result
from unified_results import (CSV_NAME, SOURCES, build_result_record,
                             make_event_csv, save_result, list_integrated_records)


class UnifiedResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='v9-record-test-')
        data = Path(self.tmp.name)
        self.patches = [
            patch.object(records, 'DATA_DIR', data),
            patch.object(records, 'RECORDS_FILE', data/'records.json'),
            patch.object(records, 'ATTACHMENTS_DIR', data/'attachments'),
        ]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()

    def test_save_virtual_normal(self):
        saved = save_result(simulate('normal'), source_kind='virtual_can', tester='担当A')
        self.assertEqual(saved['status'], '成功')
        self.assertEqual(saved['tester'], '担当A')
        self.assertEqual(saved['module'], SOURCES['virtual_can'][0])
        self.assertEqual(len(records.load_records()), 1)

    def test_virtual_failure_preserves_event_metrics(self):
        result = simulate('drop_drive_cmd')
        rec = save_result(result, source_kind='virtual_can')
        self.assertEqual(rec['status'], '失敗')
        self.assertEqual(rec['metrics']['loss_count'], result.loss_count)
        self.assertEqual(rec['metrics']['timeout_count'], result.timeout_count)
        self.assertEqual(rec['metrics']['event_count'], len(result.events))

    def test_no_landing_undecided(self):
        rec = save_result(simulate('no_landing'), source_kind='virtual_can')
        self.assertEqual(rec['status'], '未判定')

    def test_event_csv_original_order_and_count(self):
        result = simulate('drop_drive_cmd')
        lines = list(csv.DictReader(io.StringIO(make_event_csv(result, source_kind='virtual_can'))))
        self.assertEqual(len(lines), len(result.events))
        self.assertEqual([int(x['time_ms']) for x in lines], [x.time_ms for x in result.events])
        self.assertTrue(any(x['event'] == '欠落' for x in lines))

    def test_fault_propagation_notes_and_primary(self):
        result = simulate('drop_drive_cmd')
        analysis = analyze_result(result)
        record = save_result(result, source_kind='fault_analysis', analysis=analysis)
        self.assertEqual(record['metrics']['classification'], analysis.classification)
        self.assertEqual(record['metrics']['primary_time_ms'], 1000)
        path = records.ATTACHMENTS_DIR / record['id'] / CSV_NAME
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig'))))
        self.assertEqual(sum(x['is_primary_event'] == '1' for x in rows), 1)
        self.assertTrue(any(x['analysis_role'] == '波及' for x in rows))

    def test_invalid_analysis_scenario_is_rejected(self):
        result = simulate('drop_drive_cmd')
        with self.assertRaises(ValueError):
            build_result_record(result, source_kind='fault_analysis',
                                analysis=analyze_result(simulate('normal')))

    def test_requires_fault_analysis(self):
        with self.assertRaises(ValueError):
            build_result_record(simulate('normal'), source_kind='fault_analysis')

    def test_reject_unknown_source(self):
        with self.assertRaises(ValueError):
            build_result_record(simulate('normal'), source_kind='fake')

    def test_cpp_provenance_and_no_private_directory(self):
        sha = hashlib.sha256(b'known source').hexdigest()
        record, text = build_result_record(simulate('normal'), source_kind='cpp_module',
                                            cpp_sha256=sha,
                                            cpp_source='/home/example/private/controller.cpp')
        self.assertIn(sha, record['notes'])
        self.assertIn('controller.cpp', record['notes'])
        self.assertNotIn('/home/example/private', record['notes'])
        self.assertNotIn('/home/example/private', text)
        self.assertIn(sha, text)

    def test_invalid_cpp_sha_rejected(self):
        with self.assertRaises(ValueError):
            build_result_record(simulate('normal'), source_kind='cpp_module', cpp_sha256='oops')

    def test_reference_provenance_is_explicit(self):
        rec, _ = build_result_record(simulate('normal'), source_kind='virtual_can')
        self.assertIn('実機', rec['notes'])
        self.assertIn('仮想', rec['mode'])

    def test_attachment_checksum_and_share_zip(self):
        saved = save_result(simulate('normal'), source_kind='virtual_can')
        file = records.ATTACHMENTS_DIR/saved['id']/CSV_NAME
        self.assertTrue(file.is_file())
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), saved['attachments'][0]['sha256'])
        out = Path(self.tmp.name)/'share.zip'
        self.assertEqual(records.export_bundle([saved['id']],out),1)
        result = records.import_bundle(out)
        self.assertEqual(result['skipped'], 1)

    def test_dashboard_compatibility(self):
        save_result(simulate('normal'), source_kind='virtual_can')
        save_result(simulate('drop_drive_cmd'), source_kind='cpp_module')
        report = summary(records.load_records())
        self.assertEqual(report['total'],2)
        self.assertEqual(report['success'],1)
        self.assertEqual(report['failed'],1)
        self.assertEqual(report['reference'],2)
        self.assertEqual(report['non_reference'],0)
        self.assertEqual(len(module_summary(records.load_records())),2)

    def test_filter_does_not_modify_existing_records(self):
        old = records.new_record(module='着地検知', tester='古い記録', status='未判定')
        records.add_record(old)
        save_result(simulate('normal'), source_kind='virtual_can',tester='山田')
        all_records = records.load_records()
        self.assertEqual(len(list_integrated_records(all_records)),2)
        self.assertEqual(len(list_integrated_records(all_records,keyword='山田')),1)
        self.assertEqual(len(list_integrated_records(all_records,module='着地検知')),1)
        self.assertEqual(len(list_integrated_records(all_records,status='成功')),1)
        self.assertEqual(len(records.load_records()),2)


if __name__ == '__main__':
    unittest.main()
