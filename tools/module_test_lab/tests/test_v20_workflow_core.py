from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v20_workflow_core import (
    SCHEMA, inspect_csv, make_session, save_session, load_session,
    validate_session, verify_session_file,
)


def sample(tmp_path):
    file = tmp_path/'imu.csv'
    file.write_text('time_s,accel_x_mps2,gyro_z_dps\n0,0.1,0.2\n0.5,0.2,0.3\n', encoding='utf-8')
    return file


def test_inspection_and_roundtrip(tmp_path):
    f = sample(tmp_path)
    info = inspect_csv(f)
    assert info.rows == 2 and info.signals == 2
    assert info.path == str(f.resolve())
    assert len(info.sha256) == 64
    session = make_session(info, None, kind='実測', memo='BNO055 test')
    path = tmp_path/'task.json'
    save_session(session, path)
    reloaded = load_session(path)
    assert reloaded == session
    assert reloaded['schema'] == SCHEMA
    assert verify_session_file(reloaded['measured']) == info
    assert '0.1' not in path.read_text(encoding='utf-8')


def test_hash_mismatch_detected(tmp_path):
    path = sample(tmp_path)
    info = inspect_csv(path)
    path.write_text('time_s,accel_x_mps2\n0,2\n1,3\n', encoding='utf-8')
    with pytest.raises(ValueError, match='変わっています'):
        verify_session_file({'path': str(path), 'sha256': info.sha256})


def test_reference_roundtrip(tmp_path):
    a = sample(tmp_path)
    b = tmp_path/'reference.csv'
    b.write_text('time_s,accel_x_mps2\n0,0.2\n0.5,0.3\n', encoding='utf-8')
    doc = make_session(inspect_csv(a), inspect_csv(b), kind='サンプル')
    assert validate_session(doc)['reference']['path'] == str(b)


@pytest.mark.parametrize('bad', [None, [], {'schema': 'wrong'}, {'schema': SCHEMA, 'classification': '実測'}])
def test_reject_invalid_session(bad):
    with pytest.raises(ValueError):
        validate_session(bad)


def test_reject_unsafe_json_and_names(tmp_path):
    f = sample(tmp_path)
    doc = make_session(inspect_csv(f), None)
    doc['measured']['sha256'] = 'A' * 64
    with pytest.raises(ValueError, match='SHA256'):
        validate_session(doc)
    doc = make_session(inspect_csv(f), None)
    doc['measured']['path'] = 'abc\x00def'
    with pytest.raises(ValueError, match='ファイルパス'):
        validate_session(doc)
    huge = tmp_path/'huge.json'
    huge.write_text(' ' * (128*1024+1), encoding='utf-8')
    with pytest.raises(ValueError, match='128KB'):
        load_session(huge)
    bad = tmp_path/'bad.json'
    bad.write_text('{bad json', encoding='utf-8')
    with pytest.raises(json.JSONDecodeError):
        load_session(bad)


def test_no_automatic_csv_read_on_json_import(tmp_path):
    f = sample(tmp_path)
    doc = make_session(inspect_csv(f), None)
    source = tmp_path/'task.json'
    save_session(doc, source)
    f.unlink()
    assert load_session(source)['measured']['path'] == str(f)
    with pytest.raises(FileNotFoundError):
        verify_session_file(load_session(source)['measured'])


def test_reject_wrong_suffix_and_long_memo(tmp_path):
    f = sample(tmp_path)
    with pytest.raises(ValueError):
        make_session(inspect_csv(f), None, memo='x'*3001)
    with pytest.raises(ValueError):
        save_session(make_session(inspect_csv(f), None), tmp_path/'foo.txt')
    with pytest.raises(ValueError):
        inspect_csv(tmp_path/'foo.txt')
