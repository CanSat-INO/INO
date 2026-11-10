import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v20_workflow_core import CONTEXT_SCHEMA, SCHEMA, make_session, save_session, load_session, validate_session


def test_context_draft_roundtrip_without_csv(tmp_path):
    context = dict(name='静止試験', tester='担当A', hardware='ESP32-S3 / BNO055', code_version='abc123')
    doc = make_session(None, None, context=context, memo='次回は配線確認')
    path = tmp_path / 'draft.json'
    save_session(doc, path)
    assert load_session(path) == doc
    assert doc['context'] == context
    assert doc['measured'] is None


def test_legacy_json_remains_readable():
    doc = make_session(None, None, memo='以前の作業')
    restored = validate_session(doc)
    assert restored['schema'] == SCHEMA
    assert 'context' not in restored
    assert restored['memo'] == '以前の作業'


@pytest.mark.parametrize('context', [None, [], 'x', {'name': 'x' * 121}, {'tester': 1}, {'hardware': 'x' * 4001}, {'code_version': 'a\x00b'}])
def test_invalid_context_rejected(context):
    doc = make_session(None, None)
    doc['schema'] = CONTEXT_SCHEMA
    doc['context'] = context
    with pytest.raises(ValueError, match='共通実験情報'):
        validate_session(doc)


def test_invalid_new_json_does_not_overwrite_existing_file(tmp_path):
    path = tmp_path / 'draft.json'
    doc = make_session(None, None, context={'name': '保持する実験'})
    save_session(doc, path)
    original = path.read_bytes()
    bad = copy.deepcopy(doc)
    bad['context']['name'] = 'a' * 121
    with pytest.raises(ValueError):
        save_session(bad, path)
    assert path.read_bytes() == original
