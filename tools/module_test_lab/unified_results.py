"""v9: archive offline module simulation results in the existing experiment ledger.

This module never runs C++, talks to hardware, or pushes anything to GitHub.
Records are tagged as virtual; module event CSVs aren't landing-sensor traces.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
import tempfile

from module_network import Result
from records import new_record, add_record, load_records

SOURCES = {
    'virtual_can': ('3モジュール・仮想CAN', '仮想CAN（PC論理モデル）'),
    'cpp_module': ('C++モジュール連携', 'PC用C++判断＋仮想CAN'),
    'fault_analysis': ('異常分析', '仮想CAN・C++イベント分析'),
    'cpp_individual': ('Main・CAM・Drive C++個別試験', '独立PC C++3ファイル＋仮想CAN'),
}
CSV_NAME = 'module_event_timeline.csv'


def make_event_csv(result: Result, *, source_kind: str, cpp_sha256: str = '',
                   analysis=None) -> str:
    """Lossless event chronology with optional role annotations (no private paths)."""
    if source_kind not in SOURCES:
        raise ValueError('Unknown source kind')
    tags = {s.event_index: (s.role, s.explanation) for s in analysis.steps} if analysis else {}
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(('source_kind', 'scenario_key', 'evaluation', 'cpp_sha256',
                     'time_ms', 'source', 'target', 'message', 'event', 'detail',
                     'analysis_role', 'analysis_note', 'is_primary_event'))
    for i, event in enumerate(result.events):
        role, explanation = tags.get(i, ('', ''))
        writer.writerow((source_kind, result.scenario.key, result.evaluation,
                         cpp_sha256, event.time_ms, event.source, event.target,
                         event.message, event.event, event.detail, role,
                         explanation, '1' if analysis and i == analysis.primary_event_index else '0'))
    return out.getvalue()


def build_result_record(result: Result, *, source_kind: str, tester: str = '',
                        notes: str = '', cpp_sha256: str = '', cpp_source: str = '',
                        analysis=None):
    """Construct a compatible v1 record; no disk mutation."""
    if source_kind not in SOURCES:
        raise ValueError('Unsupported source kind')
    if not isinstance(result, Result):
        raise TypeError('result must be a module_network.Result')
    if analysis is not None and getattr(analysis, 'scenario_key', None) != result.scenario.key:
        raise ValueError('Analysis does not match this scenario')
    if source_kind == 'fault_analysis' and analysis is None:
        raise ValueError('Fault analysis result is required')
    if source_kind == 'virtual_can' and cpp_sha256:
        raise ValueError('Virtual CAN-only results must not have a C++ provenance hash')
    if cpp_sha256 and (len(cpp_sha256) != 64 or any(ch not in '0123456789abcdef' for ch in cpp_sha256.lower())):
        raise ValueError('Invalid SHA256')
    module, mode = SOURCES[source_kind]
    classification = str(analysis.classification) if analysis else ''
    metrics = {
        'source_kind': source_kind,
        'test_method': mode,
        'scenario_key': result.scenario.key,
        'event_count': len(result.events),
        'loss_count': result.loss_count,
        'timeout_count': result.timeout_count,
        'cpp_reject_count': sum(e.event == 'C++拒否' for e in result.events),
        'main_state': result.main_state,
        'cam_state': result.cam_state,
        'drive_state': result.drive_state,
        'cpp_sha256': cpp_sha256,
        'classification': classification,
    }
    if analysis:
        metrics['primary_time_ms'] = (result.events[analysis.primary_event_index].time_ms
                                      if analysis.primary_event_index is not None else None)
    reference_notice = ('PC上の仮想モデルによる結果です。実機CAN通信、ESP32-S3、実際の停止動作を検証した記録ではありません。')
    clean_name = Path(str(cpp_source).replace('\\', '/')).name if cpp_source else ''
    note_lines = [reference_notice, '試験方式: '+mode]
    if cpp_sha256:
        note_lines.append('C++ SHA256: '+cpp_sha256)
    if clean_name:
        note_lines.append('C++ filename: '+clean_name)
    if notes.strip():
        note_lines.append(notes.strip())
    if analysis:
        note_lines.append('異常分類: '+classification)
        note_lines.append('注意: '+analysis.caution)
    # Legacy dashboard recognizes this exact mode as a reference/synthetic result.
    # Preserve specific PC-C++/CAN mode separately in metrics and notes.
    record = new_record(module=module, mode='仮想参考モデル', tester=tester.strip(),
                        scenario=result.scenario.name,
                        code_version=('PC C++ SHA256 '+cpp_sha256[:16] if cpp_sha256
                                      else 'Module Test Lab virtual v9'),
                        status=result.evaluation if result.evaluation in ('成功', '失敗', '未判定') else '未判定',
                        expected=result.scenario.description,
                        observed=(f'Main={result.main_state} / CAM={result.cam_state} / '
                                  f'Drive={result.drive_state} / 評価={result.evaluation}'
                                  + (f' / 分類={classification}' if classification else '')),
                        notes='\n'.join(note_lines), metrics=metrics)
    return record, make_event_csv(result, source_kind=source_kind,
                                  cpp_sha256=cpp_sha256, analysis=analysis)


def save_result(result: Result, *, source_kind: str, tester: str = '',
                notes: str = '', cpp_sha256: str = '', cpp_source: str = '',
                analysis=None) -> dict:
    """Explicit local save, with an attached original event timeline.

    A separate record is produced for each explicit invocation. Callers can
    guard accidental repeated clicks if desired. No network actions occur.
    """
    record, contents = build_result_record(
        result, source_kind=source_kind, tester=tester, notes=notes,
        cpp_sha256=cpp_sha256, cpp_source=cpp_source, analysis=analysis)
    with tempfile.TemporaryDirectory(prefix='cansat-v9-') as directory:
        trace = Path(directory) / CSV_NAME
        trace.write_text(contents, encoding='utf-8-sig', newline='')
        return add_record(record, [trace])


def list_integrated_records(records=None, *, module: str = '', status: str = '',
                            keyword: str = '') -> list[dict]:
    """A subset of the existing ledger, without modifying old records."""
    if records is None:
        records = load_records()
    needle = keyword.strip().casefold()
    results = []
    for r in records:
        if module and r.get('module') != module:
            continue
        if status and r.get('status') != status:
            continue
        if needle and not any(needle in str(r.get(key, '')).casefold()
                              for key in ('tester', 'scenario', 'module', 'observed', 'notes')):
            continue
        results.append(r)
    return sorted(results, key=lambda r: (str(r.get('created_at','')), str(r.get('id',''))), reverse=True)
