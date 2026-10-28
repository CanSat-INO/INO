"""v21 read-only integrity checks for the offline CanSat Module Test Lab.

Never imports bundles or modifies the experiment ledger. Reports are intentionally
free of absolute paths and experiment contents so they can be shared after review.
This is a file-integrity check, NOT a hardware, simulation or mission certification.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from pathlib import Path
import re
import zipfile
from typing import Any

RECORD_FORMAT = 'cansat-module-lab-records'
RECORD_VERSION = 1
MAX_ATTACHMENT = 10 * 1024 * 1024
MAX_LEDGER = 16 * 1024 * 1024
MAX_BUNDLE_LEDGER = 2 * 1024 * 1024
MAX_RECORDS = 5000
MAX_ATTACHMENTS_PER_RECORD = 20
MAX_ZIP_MEMBERS = 1000
MAX_UNCOMPRESSED_BUNDLE = 120 * 1024 * 1024
HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX32 = re.compile(r'^[0-9a-f]{32}$')


@dataclass(frozen=True)
class Finding:
    level: str  # OK / WARN / ERROR
    area: str
    message: str


def _finding(level: str, area: str, message: str) -> Finding:
    return Finding(level, area, message)


def _safe_name(value: Any) -> bool:
    return (isinstance(value, str) and bool(value) and value not in ('.', '..')
            and '\\' not in value and '/' not in value and '\x00' not in value
            and Path(value).name == value and len(value) <= 255)


def _load_json_bytes(raw: bytes, *, max_bytes: int) -> dict:
    if len(raw) > max_bytes:
        raise ValueError('JSONがサイズ上限を超えています。')
    obj = json.loads(raw.decode('utf-8-sig'))
    if (not isinstance(obj, dict) or obj.get('format') != RECORD_FORMAT
            or obj.get('version') != RECORD_VERSION or not isinstance(obj.get('records'), list)):
        raise ValueError('実験記録JSONの形式が正しくありません。')
    if len(obj['records']) > MAX_RECORDS:
        raise ValueError('実験記録の件数が点検上限を超えています。')
    return obj


def _record_meta(rec: Any, ids: set[str]) -> tuple[str, list[dict]]:
    if not isinstance(rec, dict):
        raise ValueError('レコードがオブジェクトではありません。')
    rid = rec.get('id')
    if not isinstance(rid, str) or not HEX32.fullmatch(rid):
        raise ValueError('実験IDの形式が不正です。')
    if rid in ids:
        raise ValueError('実験IDが重複しています。')
    ids.add(rid)
    attachments = rec.get('attachments', [])
    if not isinstance(attachments, list) or len(attachments) > MAX_ATTACHMENTS_PER_RECORD:
        raise ValueError('添付ファイル数の形式または件数が不正です。')
    seen_names: set[str] = set()
    for a in attachments:
        if not isinstance(a, dict) or not _safe_name(a.get('name')):
            raise ValueError('添付ファイル名が不正です。')
        if a['name'].casefold() in seen_names:
            raise ValueError('同じ実験内で添付ファイル名が重複しています。')
        seen_names.add(a['name'].casefold())
        digest = a.get('sha256')
        size = a.get('bytes')
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise ValueError('添付のSHA256形式が不正です。')
        if type(size) is not int or not 0 <= size <= MAX_ATTACHMENT:
            raise ValueError('添付の記録サイズが不正です。')
    return rid, attachments


def check_local_ledger(data_dir: str | Path) -> list[Finding]:
    """Read only; do not create data directories or alter stored files."""
    home = Path(data_dir)
    ledger = home / 'records.json'
    result: list[Finding] = []
    if not ledger.exists():
        return [_finding('WARN', '記録台帳', '記録台帳はまだありません。初回利用なら正常です。')]
    if ledger.is_symlink() or not ledger.is_file():
        return [_finding('ERROR', '記録台帳', '台帳が通常のファイルではありません。')]
    try:
        if ledger.stat().st_size > MAX_LEDGER:
            return [_finding('WARN', '記録台帳', '台帳が点検上限16MBを超えています。変更せず停止しました。')]
        obj = _load_json_bytes(ledger.read_bytes(), max_bytes=MAX_LEDGER)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        return [_finding('ERROR', '記録台帳', f'台帳を読み取れません：{type(exc).__name__}')]
    items = obj['records']
    result.append(_finding('OK', '記録台帳', f'JSON形式を確認：{len(items)}件の記録'))
    ids: set[str] = set()
    checked = 0
    issues = 0
    for num, rec in enumerate(items, 1):
        if num > MAX_RECORDS:
            break
        try:
            rid, attachments = _record_meta(rec, ids)
        except ValueError as exc:
            result.append(_finding('ERROR', '記録台帳', f'{num}件目：{exc}'))
            issues += 1
            continue
        for a in attachments:
            p = home / 'attachments' / rid / a['name']
            if p.is_symlink() or not p.is_file():
                result.append(_finding('ERROR', '添付ファイル', f'{num}件目の「{a["name"]}」が見つからないかリンクです。'))
                issues += 1
                continue
            try:
                if p.stat().st_size != a['bytes']:
                    raise ValueError('記録サイズと一致しません')
                h = sha256()
                with p.open('rb') as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        h.update(chunk)
                if h.hexdigest() != a['sha256']:
                    raise ValueError('SHA256が一致しません')
                checked += 1
            except (OSError, ValueError) as exc:
                result.append(_finding('ERROR', '添付ファイル', f'{num}件目の「{a["name"]}」：{exc}'))
                issues += 1
    if issues == 0:
        result.append(_finding('OK', '添付ファイル', f'{checked}ファイルの存在・容量・SHA256を確認'))
    else:
        result.append(_finding('WARN', '添付ファイル', f'{checked}ファイル確認、{issues}件の問題があります。'))
    return result


def check_bundle(path: str | Path) -> list[Finding]:
    """Inspect ZIP member names, record metadata, and attachment hashes, without extraction."""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return [_finding('ERROR', '共有ZIP', 'ZIPファイルが見つかりません。')]
    out: list[Finding] = []
    try:
        with zipfile.ZipFile(p) as z:
            infos = z.infolist()
            if len(infos) > MAX_ZIP_MEMBERS:
                raise ValueError('ZIP内のファイル件数が点検上限を超えています。')
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BUNDLE:
                raise ValueError('ZIP展開後のサイズが点検上限を超えています。')
            names = [info.filename for info in infos]
            names_set = set(names)
            if len(names) != len(names_set) or 'records.json' not in names:
                raise ValueError('ZIPに重複名があるか records.json がありません。')
            if z.getinfo('records.json').file_size > MAX_BUNDLE_LEDGER:
                raise ValueError('records.json が2MBを超えています。')
            obj = _load_json_bytes(z.read('records.json'), max_bytes=MAX_BUNDLE_LEDGER)
            ids: set[str] = set()
            needed = {'records.json'}
            count = 0
            for rec in obj['records']:
                rid, attachments = _record_meta(rec, ids)
                for a in attachments:
                    member = f'attachments/{rid}/{a["name"]}'
                    needed.add(member)
                    if member not in names_set:
                        raise ValueError(f'添付「{a["name"]}」がZIPにありません。')
                    info = z.getinfo(member)
                    if info.file_size != a['bytes'] or info.file_size > MAX_ATTACHMENT:
                        raise ValueError(f'添付「{a["name"]}」のサイズが一致しません。')
                    h = sha256()
                    with z.open(member) as f:
                        for chunk in iter(lambda: f.read(1024 * 1024), b''):
                            h.update(chunk)
                    if h.hexdigest() != a['sha256']:
                        raise ValueError(f'添付「{a["name"]}」のSHA256が一致しません。')
                    count += 1
            extra = names_set - needed
            if extra:
                out.append(_finding('WARN', '共有ZIP', f'{len(extra)}件の未使用エントリがあります。取り込まず確認してください。'))
            out.append(_finding('OK', '共有ZIP', f'構造・添付SHA256を確認：記録{len(ids)}件／添付{count}件'))
    except (OSError, ValueError, KeyError, UnicodeError, TypeError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        out.append(_finding('ERROR', '共有ZIP', f'点検できません：{str(exc)[:200]}'))
    return out


def check_installed_files(module_dir: str | Path) -> list[Finding]:
    base = Path(module_dir)
    required = {
        '基本画面': 'app.py', 'CSV解析': 'v15_sensor_core.py',
        '実験記録': 'v16_experiment_core.py', 'C++検証': 'v14_host_runner.py',
        'フェーズ別仮想試験': 'v17_phase_core.py', '通信仮想試験': 'v18_bus_core.py',
        '比較解析': 'v19_compare_core.py', 'ワークフロー': 'v20_workflow_core.py',
    }
    # Some modules use different filename conventions; verify the actual v20 files.
    return [_finding('OK' if (base / filename).is_file() else 'ERROR', '機能構成',
                     f'{name}：{filename}' + ('' if (base / filename).is_file() else ' がありません'))
            for name, filename in required.items()]


def report_json(findings: list[Finding]) -> str:
    return json.dumps({
        'schema': 'cansat-quality-report-v21-1',
        'meaning': 'read_only_file_integrity_not_hardware_certification',
        'summary': {key: sum(f.level == key for f in findings) for key in ('OK', 'WARN', 'ERROR')},
        'findings': [asdict(f) for f in findings],
    }, indent=2, ensure_ascii=False) + '\n'


def atomic_write_text(destination: str | Path, content: str) -> None:
    """Write generated report atomically. Never follow destination symlinks."""
    import os
    import tempfile
    dest = Path(destination)
    if dest.is_symlink() or (dest.exists() and not dest.is_file()):
        raise ValueError('保存先が安全な通常ファイルではありません。')
    fd, tmp = tempfile.mkstemp(prefix='.cansat-v21-', suffix='.tmp', dir=dest.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
