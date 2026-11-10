"""Small project registration files; no experiment contents or network access."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

import project_store as store

FORMAT = 'cansat-project-share-1'
MAX_BYTES = 16 * 1024
FILTER = 'CanSat プロジェクト (*.cansat-project.json);;JSON (*.json)'


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('共有ファイルに重複した項目があります。')
        result[key] = value
    return result


def validate(document):
    if (not isinstance(document, dict) or set(document) != {'format', 'project'} or
            document.get('format') != FORMAT):
        raise ValueError('CanSatのプロジェクト共有ファイルを選んでください。実験ZIPや作業JSONとは異なります。')
    project = document.get('project')
    if not isinstance(project, dict) or set(project) != {'id', 'name', 'owner', 'purpose'}:
        raise ValueError('共有するプロジェクト情報の形式が不正です。')
    project_id = project.get('id')
    if not isinstance(project_id, str) or not store.ID_RE.fullmatch(project_id):
        raise ValueError('プロジェクトIDが不正です。')
    return {'id': project_id,
            'name': store._text(project.get('name'), 'プロジェクト名', 120, True),
            'owner': store._text(project.get('owner'), '担当者', 80),
            'purpose': store._text(project.get('purpose'), '目的', 500)}


def read_share(path):
    path = store._safe_chain(Path(path))
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('共有ファイルがないか、16KBを超えています。')
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('共有ファイルは16KB以内にしてください。')
    document = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs)
    validate(document)
    return document


def export_share(project_id, destination, root=None):
    project = store.read_project(project_id, root)
    document = {'format': FORMAT, 'project': {
        'id': project.id, 'name': project.name, 'owner': project.owner, 'purpose': project.purpose}}
    validate(document)
    raw = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    destination = store._safe_chain(Path(destination))
    # Exclusively create: never replace an existing ledger, attachment or file.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return len(raw)


@dataclass(frozen=True)
class Registration:
    project: store.Project
    created: bool
    metadata_differs: bool = False


def register(document, root=None):
    """Use exactly the shared ID. Existing projects are entirely read-only."""
    metadata = validate(document)
    project_id = metadata['id']
    base = Path(root) if root is not None else store.base_dir()
    projects = store._safe_chain(base / 'projects')
    target = store._safe_chain(projects / project_id)

    def existing():
        project = store.read_project(project_id, base)
        differs = (project.name, project.owner, project.purpose) != (
            metadata['name'], metadata['owner'], metadata['purpose'])
        return Registration(project, False, differs)

    if target.exists():
        return existing()
    projects.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.share-', dir=projects) as temp:
        stage = Path(temp)
        for folder in ('attachments', 'sessions', 'exports'):
            (stage / folder).mkdir()
        store.atomic_json(stage / 'records.json', {
            'format': 'cansat-module-lab-records', 'version': 1, 'records': []})
        store.atomic_json(stage / 'project.json', {
            'format': store.PROJECT_FORMAT, **metadata,
            'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds')})
        try:
            target.mkdir(exist_ok=False)
        except FileExistsError:
            return existing()
        # Publish project.json last. Incomplete imports never appear as projects.
        # Never remove a target directory if an I/O failure interrupts the import.
        for name in ('attachments', 'sessions', 'exports', 'records.json', 'project.json'):
            os.rename(stage / name, target / name)
    return Registration(store.read_project(project_id, base), True)
