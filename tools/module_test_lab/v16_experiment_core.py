"""Offline v16 field experiment journal built on the existing v3 records ledger.

No device access, compiler, internet or automatic judgement. Attachments are
copied with SHA256 by records.add_record; v15 CSV is validated if supplied.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import records
from v15_sensor_core import read_sensor_csv, quality_report, summary_dict

MODE = '個別実験ノート（v16）'
MODULES = ('IMU / BNO055', '気圧 / BME280', 'GNSS', 'モーター / Drive', 'カメラ / CAM',
           'Main / 状態遷移', '通信', 'その他')
PHASES = ('配線・通電確認', 'センサーデータ取得', '機能単体試験', 'フェーズ別試験', '統合前試験')
STATUSES = ('未判定', '成功', '失敗')
MAX_TEXT = 4000


def prepare_experiment(*, name: str, module: str, phase: str, tester: str = '',
                       board: str = 'ESP32-S3', code_version: str = '',
                       hardware: str = '', wiring: str = '', expected: str = '',
                       observed: str = '', notes: str = '', status: str = '未判定',
                       csv_path: str | Path | None = None,
                       code_path: str | Path | None = None) -> tuple[dict, list[Path]]:
    """Build record and validate attachments, without mutating the ledger."""
    name = name.strip()
    if not name or len(name) > 120:
        raise ValueError('実験名は1～120文字で入力してください。')
    if module not in MODULES or phase not in PHASES or status not in STATUSES:
        raise ValueError('対象機能・開発段階・結果の選択値が不正です。')
    fields = dict(tester=tester, board=board, code_version=code_version,
                  hardware=hardware, wiring=wiring, expected=expected,
                  observed=observed, notes=notes)
    if any(len(v) > MAX_TEXT for v in fields.values()):
        raise ValueError('各入力欄は4000文字以内にしてください。')
    attachments: list[Path] = []
    data: dict = {}
    if csv_path:
        p = Path(csv_path).expanduser()
        _check_attachment(p, '.csv')
        log = read_sensor_csv(p)
        summary = summary_dict(log)
        data = {
            'filename': p.name, 'rows': log.row_count,
            'signals': sorted(log.signals),
            'time_kind': log.time_kind, 'sha256': log.source_sha256,
            'issues': list(quality_report(log)),
            'summary': summary,
        }
        attachments.append(p)
    if code_path:
        p = Path(code_path).expanduser()
        _check_attachment(p, '.ino', '.cpp', '.hpp', '.h', '.c', '.txt')
        attachments.append(p)
    if len({p.name.casefold() for p in attachments}) != len(attachments):
        raise ValueError('CSVとコードのファイル名が同一です。異なる名前にしてください。')
    record = records.new_record(
        module=module, tester=tester.strip(), mode=MODE, scenario=name,
        code_version=code_version.strip(), status=status,
        expected=expected.strip(), observed=observed.strip(), notes=notes.strip(),
        metrics={'v16': {
            'phase': phase, 'board': board.strip(), 'hardware': hardware.strip(),
            'wiring': wiring.strip(), 'log': data,
        }},
    )
    return record, attachments


def _check_attachment(p: Path, *suffixes: str) -> None:
    if p.is_symlink() or not p.is_file():
        raise ValueError(f'ファイルが見つからないか、リンクです: {p}')
    if p.suffix.casefold() not in suffixes:
        raise ValueError(f'対応していないファイル形式です: {p.name}')
    if not 0 < p.stat().st_size <= records.MAX_ATTACHMENT_BYTES:
        raise ValueError(f'ファイルは1バイト～10MB以内にしてください: {p.name}')


def save_experiment(**kwargs) -> dict:
    record, paths = prepare_experiment(**kwargs)
    # Save only after all user inputs and attachment contents are checked.
    return records.add_record(record, paths)


def experiment_records(items: list[dict] | None = None, *, search: str = '',
                       module: str = '', phase: str = '') -> list[dict]:
    items = records.load_records() if items is None else items
    needle = search.strip().casefold()
    result = []
    for item in items:
        if item.get('mode') != MODE:
            continue
        meta = item.get('metrics', {}).get('v16', {})
        if module and item.get('module') != module:
            continue
        if phase and meta.get('phase') != phase:
            continue
        haystack = ' '.join(str(item.get(k, '')) for k in
                            ('module', 'scenario', 'tester', 'code_version', 'status', 'observed', 'notes'))
        haystack += ' ' + ' '.join(str(meta.get(k, '')) for k in ('phase', 'board', 'hardware', 'wiring'))
        if needle and needle not in haystack.casefold():
            continue
        result.append(item)
    return sorted(result, key=lambda r: (r.get('created_at',''), r.get('id','')), reverse=True)


def summary_counts(items: list[dict]) -> dict[str, int]:
    return {'total': len(items), **{key: sum(x.get('status') == key for x in items)
                                   for key in STATUSES}}


def record_details(record: dict) -> str:
    v = record.get('metrics', {}).get('v16', {})
    log = v.get('log', {})
    details = [
        f"実験ID: {record.get('id','')}", f"日時: {record.get('created_at','')}",
        f"実験名: {record.get('scenario','')}", f"対象: {record.get('module','')}",
        f"開発段階: {v.get('phase','')}", f"担当者: {record.get('tester','')}",
        f"基板: {v.get('board','')}", f"コード版: {record.get('code_version','')}",
        f"配線・使用機器: {v.get('hardware','')} / {v.get('wiring','')}",
        f"結果（担当者入力）: {record.get('status','')}",
        f"期待動作: {record.get('expected','')}", f"観測結果: {record.get('observed','')}",
        f"メモ: {record.get('notes','')}",
    ]
    if log:
        details += [f"CSV: {log.get('filename','')}", f"データ数: {log.get('rows',0)}",
                    f"信号: {', '.join(log.get('signals',[]))}",
                    f"CSV SHA256: {log.get('sha256','')}"]
        details += [f'データ品質（参考）: {x}' for x in log.get('issues', [])]
    details.append('添付ファイル：')
    for a in record.get('attachments', []):
        details.append(f"  {a.get('name','')}  {a.get('bytes',0)} bytes  SHA256={a.get('sha256','')}")
    return '\n'.join(details)


def _excel_safe(value) -> str:
    value = str(value or '')
    if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
        return "'" + value
    return value


def export_experiment_csv(items: list[dict], path: Path) -> int:
    headers = ('ID', '日時', '実験名', 'モジュール', '開発段階', '担当者', '基板',
               'コード版', '判定', '期待動作', '観測結果', '使用機器', '配線',
               'メモ', 'ログ行数', 'ログ信号', '添付ファイル')
    with Path(path).open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for rec in items:
            info = rec.get('metrics', {}).get('v16', {})
            log = info.get('log', {})
            row = [rec.get('id',''), rec.get('created_at',''), rec.get('scenario',''),
                   rec.get('module',''), info.get('phase',''), rec.get('tester',''),
                   info.get('board',''), rec.get('code_version',''), rec.get('status',''),
                   rec.get('expected',''), rec.get('observed',''), info.get('hardware',''),
                   info.get('wiring',''), rec.get('notes',''), log.get('rows',''),
                   '; '.join(log.get('signals', [])),
                   '; '.join(a.get('name','') for a in rec.get('attachments',[]))]
            writer.writerow([_excel_safe(value) for value in row])
    return len(items)
