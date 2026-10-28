from __future__ import annotations
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

import pytest
from v21_quality_core import (check_local_ledger, check_bundle, check_installed_files,
                              report_json, Finding, atomic_write_text)
from v20_workflow_core import save_session, load_session, SCHEMA


@pytest.fixture
def fixture(tmp_path):
    rid = '0' * 32
    raw = b'time_s,accel_x_mps2\n0,9.81\n'
    dest = tmp_path / 'attachments' / rid
    dest.mkdir(parents=True)
    (dest / 'log.csv').write_bytes(raw)
    rec = dict(id=rid, scenario='experiment', attachments=[dict(name='log.csv', bytes=len(raw),
                                                                  sha256=hashlib.sha256(raw).hexdigest())])
    obj = dict(format='cansat-module-lab-records', version=1, records=[rec])
    (tmp_path / 'records.json').write_text(json.dumps(obj), encoding='utf-8')
    z = tmp_path / 'bundle.zip'
    with zipfile.ZipFile(z, 'w') as f:
        f.writestr('records.json', json.dumps(obj))
        f.writestr(f'attachments/{rid}/log.csv', raw)
    return tmp_path, z, obj


def test_no_ledger_creates_nothing(tmp_path):
    base = tmp_path / 'notcreated'
    report = check_local_ledger(base)
    assert report[0].level == 'WARN' and not base.exists()


def test_local_success(fixture):
    directory, _, _ = fixture
    assert [x.level for x in check_local_ledger(directory)] == ['OK','OK']


def test_missing_attachment_detected_without_mutation(fixture):
    directory, _, _ = fixture
    (directory / 'attachments' / ('0' * 32) / 'log.csv').unlink()
    report = check_local_ledger(directory)
    assert 'ERROR' in [x.level for x in report]
    assert not (directory / 'attachments' / ('0' * 32) / 'log.csv').exists()  # 点検では再生成しない


def test_hash_mismatch_detected(fixture):
    directory, _, _ = fixture
    p = directory / 'attachments' / ('0' * 32) / 'log.csv'
    p.write_bytes(b'Z' * p.stat().st_size)
    assert 'SHA256' in ' '.join(x.message for x in check_local_ledger(directory))


def test_bundle_success(fixture):
    _, z, _ = fixture
    assert [f.level for f in check_bundle(z)] == ['OK']


def test_bundle_missing_attachment(fixture, tmp_path):
    _, _, obj = fixture
    path = tmp_path / 'no-attachment.zip'
    with zipfile.ZipFile(path, 'w') as f:
        f.writestr('records.json', json.dumps(obj))
    assert check_bundle(path)[0].level == 'ERROR'


def test_bundle_bad_sha(fixture, tmp_path):
    _, _, obj = fixture
    path = tmp_path / 'tampered.zip'
    with zipfile.ZipFile(path, 'w') as f:
        f.writestr('records.json', json.dumps(obj))
        f.writestr(f'attachments/{"0"*32}/log.csv', b'x'*len(b'time_s,accel_x_mps2\n0,9.81\n'))
    assert check_bundle(path)[0].level == 'ERROR'


def test_bundle_duplicate_id(fixture, tmp_path):
    _, _, obj = fixture
    obj['records'].append(dict(obj['records'][0]))
    path = tmp_path / 'dups.zip'
    with zipfile.ZipFile(path, 'w') as f:
        f.writestr('records.json', json.dumps(obj))
    assert check_bundle(path)[0].level == 'ERROR'


def test_bundle_malicious_filename(fixture, tmp_path):
    _, _, obj = fixture
    obj['records'][0]['attachments'][0]['name'] = '../bad.csv'
    path = tmp_path / 'traversal.zip'
    with zipfile.ZipFile(path, 'w') as f:
        f.writestr('records.json', json.dumps(obj))
    assert check_bundle(path)[0].level == 'ERROR'


def test_bundle_not_unzipped(fixture):
    directory, z, _ = fixture
    (directory / 'attachments' / ('0' * 32) / 'log.csv').unlink()
    _ = check_bundle(z)
    assert not (directory / 'attachments' / ('0' * 32) / 'log.csv').exists()


def test_report_contains_counts_without_file_content():
    result = report_json([Finding('WARN','台帳','注意')])
    data = json.loads(result)
    assert data['summary'] == {'OK': 0, 'WARN': 1, 'ERROR': 0}


def test_atomic_writer_keeps_previous_on_replace_error(tmp_path, monkeypatch):
    p = tmp_path / 'existing.json'
    p.write_text('old', encoding='utf-8')
    import os
    def reject(*args):
        raise OSError('disk not ready')
    monkeypatch.setattr(os, 'replace', reject)
    with pytest.raises(OSError):
        atomic_write_text(p, 'new')
    assert p.read_text() == 'old'
    assert sorted(x.name for x in tmp_path.iterdir()) == ['existing.json']


def test_atomic_writer_rejects_symlink(tmp_path):
    dest = tmp_path / 'dest'
    dest.write_text('old')
    link = tmp_path / 'link'
    link.symlink_to(dest)
    with pytest.raises(ValueError):
        atomic_write_text(link, 'new')
    assert dest.read_text() == 'old'


def test_v20_session_roundtrip_atomic(tmp_path):
    f = tmp_path / 'work.json'
    obj = {'schema': SCHEMA, 'classification':'サンプル', 'measured':None,
           'reference':None, 'memo':'日本語メモ', 'meaning':'workflow_bookmark_not_hardware_validation'}
    save_session(obj, f)
    assert load_session(f) == obj


def test_check_install_complete():
    base = Path(__file__).resolve().parents[1]
    assert all(f.level == 'OK' for f in check_installed_files(base))
