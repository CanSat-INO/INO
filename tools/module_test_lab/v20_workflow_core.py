"""v20 offline workflow handoff: metadata only, never executes imported code.

The workflow document is NOT an experiment result or certificate. References
are paths plus hashes, and files are only opened on an explicit user action.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from v15_sensor_core import read_sensor_csv

SCHEMA = 'cansat-module-lab-workflow-v20-1'
CONTEXT_SCHEMA = 'cansat-module-lab-workflow-v20-2'
CONTEXT_LIMITS = {'name': 120, 'tester': 4000, 'hardware': 4000, 'code_version': 4000}
KINDS = ('サンプル', '実測', '仮想')
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_MEMO_CHARS = 3000
MAX_PATH_CHARS = 4096


@dataclass(frozen=True)
class CsvInfo:
    path: str
    name: str
    sha256: str
    rows: int
    signals: int
    time_kind: str


def inspect_csv(path: str | Path) -> CsvInfo:
    """Reuse the existing parser and its caps; no implicit CSV conversion."""
    p = Path(path).expanduser()
    if p.suffix.lower() != '.csv':
        raise ValueError('CSVファイル（.csv）を選択してください。')
    p = p.resolve(strict=True)
    if not p.is_file():
        raise ValueError('CSVファイル（.csv）を選択してください。')
    log = read_sensor_csv(p)
    return CsvInfo(str(p), p.name, log.source_sha256, log.row_count,
                   len(log.signals), log.time_kind)


def _path(value: Any) -> str:
    if not isinstance(value, str) or len(value) > MAX_PATH_CHARS or '\x00' in value:
        raise ValueError('不正なファイルパスです。')
    return value.strip()


def validate_context(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ValueError('共通実験情報が不正です。')
    result = {}
    for key, limit in CONTEXT_LIMITS.items():
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > limit or '\x00' in text:
            raise ValueError(f'共通実験情報 {key} は{limit}文字以内で入力してください。')
        result[key] = text
    return result


def make_session(measured: CsvInfo | None, reference: CsvInfo | None,
                 *, kind: str = 'サンプル', memo: str = '', context: dict | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError('ログの種別が不正です。')
    if not isinstance(memo, str) or len(memo) > MAX_MEMO_CHARS:
        raise ValueError('メモは3000文字以内にしてください。')
    def entry(info):
        return None if info is None else {'path': info.path, 'sha256': info.sha256,
                                          'rows': info.rows, 'signals': info.signals}
    result = {
        'schema': SCHEMA, 'classification': kind, 'measured': entry(measured),
        'reference': entry(reference), 'memo': memo,
        'meaning': 'workflow_bookmark_not_hardware_validation',
    }
    if context is not None:
        result.update(schema=CONTEXT_SCHEMA, context=validate_context(context))
    return result


def validate_session(value: Any) -> dict:
    if not isinstance(value, dict) or value.get('schema') not in (SCHEMA, CONTEXT_SCHEMA):
        raise ValueError('v20作業ファイルではありません。')
    if value.get('meaning') != 'workflow_bookmark_not_hardware_validation':
        raise ValueError('作業ファイルの種別が不正です。')
    kind = value.get('classification')
    if kind not in KINDS:
        raise ValueError('ログ種別が不正です。')
    memo = value.get('memo')
    if not isinstance(memo, str) or len(memo) > MAX_MEMO_CHARS:
        raise ValueError('メモが不正です。')
    verified = {}
    for field in ('measured', 'reference'):
        info = value.get(field)
        if info is None:
            verified[field] = None
            continue
        if not isinstance(info, dict):
            raise ValueError(f'{field} の情報が不正です。')
        path = _path(info.get('path'))
        digest = info.get('sha256')
        if not path or not isinstance(digest, str) or len(digest) != 64 or any(
            ch not in '0123456789abcdef' for ch in digest):
            raise ValueError(f'{field} のパスまたはSHA256が不正です。')
        rows = info.get('rows')
        signals = info.get('signals')
        if type(rows) is not int or type(signals) is not int or not (0 < rows <= 1_000_000) or not (0 < signals <= 10000):
            raise ValueError(f'{field} の行・信号数が不正です。')
        verified[field] = {'path': path, 'sha256': digest, 'rows': rows, 'signals': signals}
    result = {'schema': value['schema'], 'classification': kind, 'memo': memo,
            'measured': verified['measured'], 'reference': verified['reference'],
            'meaning': 'workflow_bookmark_not_hardware_validation'}
    if value['schema'] == CONTEXT_SCHEMA:
        result['context'] = validate_context(value.get('context'))
    if "project_id" in value:
        import re
        project_id = value["project_id"]
        if not isinstance(project_id, str) or (project_id != "legacy" and re.fullmatch(r"[0-9a-f]{32}", project_id) is None):
            raise ValueError("作業JSONのプロジェクトIDが不正です。")
        result["project_id"] = project_id
    return result


def save_session(value: dict, destination: str | Path) -> None:
    obj = validate_session(value)
    p = Path(destination)
    if p.suffix.lower() != '.json':
        raise ValueError('保存先はJSONファイルにしてください。')
    from v21_quality_core import atomic_write_text
    atomic_write_text(p, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def load_session(source: str | Path) -> dict:
    p = Path(source)
    if p.suffix.lower() != '.json' or p.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError('v20 JSONファイルを選択してください（128KB以内）。')
    return validate_session(json.loads(p.read_text(encoding='utf-8')))


def verify_session_file(info: dict | None) -> CsvInfo | None:
    """Manual post-import verification, never triggered by JSON loading."""
    if info is None:
        return None
    parsed = inspect_csv(info['path'])
    if parsed.sha256 != info['sha256']:
        raise ValueError(f'{parsed.name} は保存時と内容が変わっています。')
    return parsed
