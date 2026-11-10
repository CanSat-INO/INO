"""Project metadata and fixed storage paths. Standard library only.

The selected project is fixed at process startup so imported module constants
and background workers cannot accidentally retain a different project's paths.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

PROJECT_ENV = 'CANSAT_LAB_PROJECT_ID'
PROJECT_FORMAT = 'cansat-lab-project-1'
ID_RE = re.compile(r'^[0-9a-f]{32}$')
MAX_METADATA = 16 * 1024


def base_dir() -> Path:
    return Path.home() / 'cansat_module_lab_data'


def active_id() -> str | None:
    value = os.environ.get(PROJECT_ENV)
    if value is not None and not ID_RE.fullmatch(value):
        raise ValueError('プロジェクトIDが不正です。トップから選び直してください。')
    return value


def _safe_chain(path: Path) -> Path:
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError('保存先にシンボリックリンクがあります。')
    return path


def atomic_json(path: Path, value: dict) -> None:
    path = _safe_chain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    fd, name = tempfile.mkstemp(prefix='.project-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    owner: str
    purpose: str
    directory: Path


def _text(value, label, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise ValueError(f'{label}は{limit}文字以内で入力してください。')
    value = value.strip()
    if required and not value:
        raise ValueError(f'{label}を入力してください。')
    return value


def read_project(project_id: str, root: Path | None = None) -> Project:
    if not isinstance(project_id, str) or not ID_RE.fullmatch(project_id):
        raise ValueError('プロジェクトIDが不正です。')
    directory = _safe_chain((Path(root) if root is not None else base_dir()) / 'projects' / project_id)
    path = directory / 'project.json'
    _safe_chain(path)
    if not path.is_file() or path.stat().st_size > MAX_METADATA:
        raise ValueError('プロジェクト情報がないか、大きすぎます。')
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or obj.get('format') != PROJECT_FORMAT or obj.get('id') != project_id:
        raise ValueError('プロジェクト情報の形式が不正です。')
    return Project(project_id, _text(obj.get('name'), 'プロジェクト名', 120, True),
                   _text(obj.get('owner', ''), '担当者', 80),
                   _text(obj.get('purpose', ''), '目的', 500), directory)


def list_projects(root: Path | None = None) -> tuple[list[Project], int]:
    parent = _safe_chain((Path(root) if root is not None else base_dir()) / 'projects')
    if not parent.exists():
        return [], 0  # Opening the top page creates no ledger or data folders.
    projects, invalid = [], 0
    for directory in sorted(parent.iterdir()):
        if not ID_RE.fullmatch(directory.name):
            continue
        try:
            projects.append(read_project(directory.name, root))
        except (ValueError, OSError, UnicodeError):
            invalid += 1
    return sorted(projects, key=lambda p: (p.name.casefold(), p.id)), invalid


def create_project(name: str, owner: str = '', purpose: str = '', root: Path | None = None) -> Project:
    name = _text(name, 'プロジェクト名', 120, True)
    owner = _text(owner, '担当者', 80)
    purpose = _text(purpose, '目的', 500)
    project_id = uuid.uuid4().hex
    directory = _safe_chain((Path(root) if root is not None else base_dir()) / 'projects' / project_id)
    directory.mkdir(parents=True, exist_ok=False)
    # A directory without project.json is not advertised as a usable project.
    for folder in ('attachments', 'sessions', 'exports'):
        (directory / folder).mkdir()
    atomic_json(directory / 'records.json', {'format': 'cansat-module-lab-records', 'version': 1, 'records': []})
    atomic_json(directory / 'project.json', {'format': PROJECT_FORMAT, 'id': project_id,
                'name': name, 'owner': owner, 'purpose': purpose,
                'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
    return read_project(project_id, root)


def data_dir() -> Path:
    project_id = active_id()
    return read_project(project_id).directory if project_id else base_dir()


def project_title() -> str:
    project_id = active_id()
    return read_project(project_id).name if project_id else '既存の実験（未分類）'


def backup_dir() -> Path:
    project_id = active_id()
    return base_dir() / 'project_backups' / project_id if project_id else Path.home() / 'cansat_module_lab_backups'


def trash_dir() -> Path:
    project_id = active_id()
    return base_dir() / 'project_trash' / project_id if project_id else Path.home() / 'cansat_module_lab_trash'


def export_path(filename: str, *, session=False) -> str:
    if Path(filename).name != filename or '/' in filename or '\\' in filename:
        raise ValueError('出力ファイル名が不正です。')
    if not active_id():
        return str(Path.home() / filename)
    directory = _safe_chain(data_dir() / ('sessions' if session else 'exports'))
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory / filename)


def record_matches(record: dict) -> bool:
    """Unclassified and named-project records never mix during network import."""
    return record.get('project_id') == active_id()


def validate_record_project(record: dict, *, allow_unclassified=False) -> dict:
    if not isinstance(record, dict):
        raise ValueError('記録の形式が不正です。')
    target = active_id()
    source = record.get('project_id')
    if source == target:
        return record
    if source is None and target and allow_unclassified:
        return {**record, 'project_id': target}
    raise ValueError('別プロジェクトの記録です。対応するプロジェクトを開いてください。')


def bootstrap_cli(argv=None):
    parser = argparse.ArgumentParser(description='CanSat Simulation')
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--project', help='保存済みプロジェクトのID')
    choice.add_argument('--legacy', action='store_true', help='従来の未分類台帳を開く')
    args = parser.parse_args(argv)
    if args.project:
        read_project(args.project)
        os.environ[PROJECT_ENV] = args.project
    else:
        os.environ.pop(PROJECT_ENV, None)
    return args
