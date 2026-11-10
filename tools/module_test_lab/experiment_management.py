"""v12 virtual-CAN experiment plans, batch runs and local history.

Offline, standard-library-only; never invokes ROS 2, Gazebo, C++ or hardware.
Robot and environment parameters are recorded but NOT applied to the simulator.
"""
from __future__ import annotations

import csv
import io
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

from module_network import SCENARIOS, simulate
from simulation_common import CommonFormatError, default_config, make_run, validate_config

PLAN_SCHEMA = 'cansat.experiment.plan'
BATCH_SCHEMA = 'cansat.experiment.batch'
FORMAT_VERSION = 1
MAX_CASES = 40
MAX_BYTES = 5_000_000
from records import DATA_DIR
HISTORY_DIR = DATA_DIR / 'v12_experiment_batches'
_ID = re.compile(r'^[0-9a-f]{32}$')


class ExperimentError(ValueError):
    """Bad user-supplied experiment plan or stored result."""


def _label(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 100 or any(ord(c) < 32 for c in value):
        raise ExperimentError(f'{field}は1〜100文字の文字列で入力してください。')
    return value.strip()


def new_plan(name='仮想CAN比較実験'):
    return {'schema': PLAN_SCHEMA, 'version': FORMAT_VERSION, 'name': name, 'cases': []}


def make_case(config, label):
    return {'label': _label(label, '条件名'), 'config': validate_config(config)}


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) != {'schema', 'version', 'name', 'cases'}:
        raise ExperimentError('実験計画の項目が不正です。')
    if plan['schema'] != PLAN_SCHEMA or type(plan['version']) is not int or plan['version'] != FORMAT_VERSION:
        raise ExperimentError('未対応の実験計画形式です。')
    name = _label(plan['name'], '実験名')
    cases = plan['cases']
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ExperimentError(f'実験条件は1〜{MAX_CASES}件にしてください。')
    normalized = []
    for i, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) != {'label', 'config'}:
            raise ExperimentError(f'{i+1}番目の条件の項目が不正です。')
        try:
            normalized.append(make_case(case['config'], case['label']))
        except (CommonFormatError, ExperimentError) as exc:
            raise ExperimentError(f'{i+1}番目の条件: {exc}') from exc
    return {'schema': PLAN_SCHEMA, 'version': FORMAT_VERSION, 'name': name, 'cases': normalized}


def plan_json(plan):
    return json.dumps(validate_plan(plan), ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def parse_plan(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise ExperimentError('実験計画が大きすぎます。')
    try:
        return validate_plan(json.loads(text, parse_constant=_invalid_constant))
    except (ValueError, TypeError) as exc:
        raise ExperimentError(f'実験計画JSONが不正です: {exc}') from exc


def _invalid_constant(value):
    raise ExperimentError(f'{value}は使用できません。')


def read_text_limited(path):
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ExperimentError('ファイルが大きすぎます。')
    return p.read_text(encoding='utf-8-sig')


def _summary(run):
    result = run['result']
    return {'evaluation': result['evaluation'], 'main_state': result['main_state'],
            'cam_state': result['cam_state'], 'drive_state': result['drive_state'],
            'loss_count': result['loss_count'], 'timeout_count': result['timeout_count'],
            'event_count': len(run['samples'])}


def run_plan(plan, *, created_at=None, batch_id=None):
    """Run each saved virtual-CAN scenario once; no implicit stochastic repetitions."""
    normalized = validate_plan(plan)
    outcomes = []
    for case in normalized['cases']:
        cfg = case['config']
        result = simulate(cfg['scenario']['key'])
        run = make_run(cfg, result, created_at=created_at)
        outcomes.append({'label': case['label'], 'scenario_key': cfg['scenario']['key'],
                         'summary': _summary(run), 'run': run})
    identifier = batch_id or uuid4().hex
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        raise ExperimentError('実験IDが不正です。')
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return {'schema': BATCH_SCHEMA, 'version': FORMAT_VERSION, 'id': identifier,
            'created_at': timestamp, 'plan': normalized, 'outcomes': outcomes,
            'engine': 'ino.virtual_can.v8', 'physical_parameters_applied': False,
            'limitations': ('同一シナリオは決定論的な論理イベントを返します。質量・タイヤ・地形・初期状態は'
                            '結果に作用しません。成功率は実機信頼性や走破率ではありません。')}


def _validate_batch(batch):
    if not isinstance(batch, dict) or set(batch) != {'schema','version','id','created_at','plan','outcomes',
                                                      'engine','physical_parameters_applied','limitations'}:
        raise ExperimentError('実験結果の項目が不正です。')
    if batch['schema'] != BATCH_SCHEMA or type(batch['version']) is not int or batch['version'] != FORMAT_VERSION:
        raise ExperimentError('実験結果のバージョンが不正です。')
    if not isinstance(batch['id'], str) or not _ID.fullmatch(batch['id']):
        raise ExperimentError('実験IDが不正です。')
    if not isinstance(batch['created_at'], str) or len(batch['created_at']) > 80:
        raise ExperimentError('実験日時が不正です。')
    plan = validate_plan(batch['plan'])
    outcomes = batch['outcomes']
    if not isinstance(outcomes, list) or len(outcomes) != len(plan['cases']):
        raise ExperimentError('実験結果の件数が一致しません。')
    if batch['engine'] != 'ino.virtual_can.v8' or batch['physical_parameters_applied'] is not False:
        raise ExperimentError('実験エンジンまたは物理計算フラグが不正です。')
    if not isinstance(batch['limitations'], str):
        raise ExperimentError('制限事項が不正です。')
    for case, item in zip(plan['cases'], outcomes):
        if not isinstance(item, dict) or set(item) != {'label','scenario_key','summary','run'}:
            raise ExperimentError('条件の結果構造が不正です。')
        if item['label'] != case['label'] or item['scenario_key'] != case['config']['scenario']['key']:
            raise ExperimentError('条件と結果が一致しません。')
        if not isinstance(item['summary'], dict) or set(item['summary']) != {
            'evaluation','main_state','cam_state','drive_state','loss_count','timeout_count','event_count'}:
            raise ExperimentError('比較項目が不正です。')
        if not isinstance(item['run'], dict) or item['run'].get('config') != case['config'] or \
                item['run'].get('physical_parameters_applied') is not False or \
                item['run'].get('schema') != 'cansat.simulation.run':
            raise ExperimentError('保存済み実行データが設定と一致しません。')
        if not isinstance(item['run'].get('samples'), list) or len(item['run']['samples']) > 500:
            raise ExperimentError('イベントデータが不正です。')
        if item['summary'] != _summary(item['run']):
            raise ExperimentError('比較項目とイベント数が一致しません。')
    return batch


def batch_json(batch):
    return json.dumps(_validate_batch(batch), ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def parse_batch(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_BYTES:
        raise ExperimentError('実験結果ファイルが大きすぎます。')
    try:
        return _validate_batch(json.loads(text, parse_constant=_invalid_constant))
    except (ValueError, TypeError, KeyError) as exc:
        raise ExperimentError(f'実験結果JSONが不正です: {exc}') from exc


def batch_csv(batch):
    _validate_batch(batch)
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['experiment_id','experiment_name','case_no','case_label','scenario_key',
                     'robot_name','mass_kg','wheel_diameter_m','wheel_width_m','motor_max_torque_nm',
                     'terrain','step_height_m','gravity_mps2','evaluation','main_state','cam_state',
                     'drive_state','loss_count','timeout_count','event_count','physical_parameters_applied'])
    for i, (case, item) in enumerate(zip(batch['plan']['cases'], batch['outcomes']), 1):
        r, e, s = case['config']['robot'],case['config']['environment'],item['summary']
        writer.writerow([batch['id'],batch['plan']['name'],i,case['label'],item['scenario_key'],
                         r['name'],r['mass_kg'],r['wheel_diameter_m'],r['wheel_width_m'],r['motor_max_torque_nm'],
                         e['terrain'],e['step_height_m'],e['gravity_mps2'],s['evaluation'],s['main_state'],
                         s['cam_state'],s['drive_state'],s['loss_count'],s['timeout_count'],
                         s['event_count'],False])
    return out.getvalue()


def save_history(batch, directory=None):
    """Save immutable local result under a random ID; never touches v9 ledger or GitHub."""
    payload = batch_json(batch)
    if len(payload.encode('utf-8')) > MAX_BYTES:
        raise ExperimentError('実験結果が大きすぎるため保存できません。')
    base = Path(directory) if directory is not None else HISTORY_DIR
    base.mkdir(parents=True, exist_ok=True)
    target = base / f"{batch['id']}.json"
    # Exclusive open avoids replacing a prior experiment, even if a caller supplies an ID.
    with target.open('x', encoding='utf-8') as handle:
        handle.write(payload)
    return target


def load_history(identifier, directory=None):
    if not isinstance(identifier, str) or not _ID.fullmatch(identifier):
        raise ExperimentError('実験IDが不正です。')
    base = Path(directory) if directory is not None else HISTORY_DIR
    result = parse_batch(read_text_limited(base / f'{identifier}.json'))
    if result['id'] != identifier:
        raise ExperimentError('ファイル名と実験IDが一致しません。')
    return result


def list_history(directory=None, limit=100):
    """Return newest saved metadata without loading arbitrary files outside the history folder."""
    base = Path(directory) if directory is not None else HISTORY_DIR
    if not base.is_dir():
        return []
    entries = sorted((p for p in base.iterdir() if p.is_file() and _ID.fullmatch(p.stem)
                      and p.suffix == '.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for p in entries[:limit]:
        try:
            batch = load_history(p.stem, base)
        except (OSError, UnicodeError, ExperimentError):
            continue
        outcomes = batch['outcomes']
        rows.append({'id': batch['id'], 'created_at': batch['created_at'],
                     'name': batch['plan']['name'], 'count': len(outcomes),
                     'success': sum(x['summary']['evaluation'] == '成功' for x in outcomes),
                     'failure': sum(x['summary']['evaluation'] == '失敗' for x in outcomes)})
    return rows


def default_scenario_plan(name='仮想CAN 8シナリオ比較', config=None):
    cfg = validate_config(config if config is not None else default_config())
    plan = new_plan(name)
    for scenario in SCENARIOS:
        case_cfg = validate_config(cfg)
        case_cfg['scenario']['key'] = scenario.key
        plan['cases'].append(make_case(case_cfg, scenario.name))
    return validate_plan(plan)
