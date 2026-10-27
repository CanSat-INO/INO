"""v11 portable, versioned CanSat configuration and virtual event interchange.

No ROS2, Qt, physics engine, hardware, or C++ dependency. Physical fields are
metadata only in v11; the existing virtual-CAN simulator does not consume them.
"""
from __future__ import annotations

import csv
import io
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 'cansat.simulation.common'
VERSION = 1
RUN_SCHEMA = 'cansat.simulation.run'
MAX_FILE_BYTES = 1_000_000

DEFAULT_CONFIG = {
    'schema': SCHEMA,
    'version': VERSION,
    'robot': {
        'name': 'INO-demo', 'mass_kg': 0.8,
        'center_of_mass_m': [0.0, 0.0, 0.05],
        'wheel_diameter_m': 0.06, 'wheel_width_m': 0.025,
        'motor_max_torque_nm': 0.15,
    },
    'environment': {
        'terrain': 'flat', 'step_height_m': 0.02,
        'gravity_mps2': 9.80665,
    },
    'initial_state': {
        'position_m': [0.0, 0.0, 0.0],
        'orientation_xyzw': [0.0, 0.0, 0.0, 1.0],
        'velocity_mps': [0.0, 0.0, 0.0],
    },
    'scenario': {'key': 'normal'},
}


class CommonFormatError(ValueError):
    pass


def _keys(obj, expected, label):
    if not isinstance(obj, dict) or set(obj) != set(expected):
        raise CommonFormatError(f'{label}: 必須キーまたは余分なキーを確認してください。')


def _string(value, label, limit=80):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise CommonFormatError(f'{label}: 文字列が不正です。')
    return value


def _number(value, label, low=None, high=None):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise CommonFormatError(f'{label}: 有限の数値が必要です。')
    if (low is not None and value < low) or (high is not None and value > high):
        raise CommonFormatError(f'{label}: 許容範囲外です。')
    return float(value)


def _vector(value, n, label, low=-1e6, high=1e6):
    if not isinstance(value, list) or len(value) != n:
        raise CommonFormatError(f'{label}: {n}要素の配列が必要です。')
    return [_number(x, f'{label}[{i}]', low, high) for i, x in enumerate(value)]


def validate_config(config):
    """Return canonical validated copy. Reject unknown schema fields and NaN."""
    _keys(config, DEFAULT_CONFIG, '設定')
    if config['schema'] != SCHEMA or type(config['version']) is not int or config['version'] != VERSION:
        raise CommonFormatError('未対応の設定スキーマまたはバージョンです。')
    r, e, s, sc = (config[x] for x in ('robot','environment','initial_state','scenario'))
    _keys(r, DEFAULT_CONFIG['robot'], 'robot')
    _keys(e, DEFAULT_CONFIG['environment'], 'environment')
    _keys(s, DEFAULT_CONFIG['initial_state'], 'initial_state')
    _keys(sc, DEFAULT_CONFIG['scenario'], 'scenario')
    _string(r['name'], '機体名')
    for k in ('mass_kg','wheel_diameter_m','wheel_width_m','motor_max_torque_nm'):
        _number(r[k], k, 0.000001, 10000)
    _vector(r['center_of_mass_m'], 3, 'center_of_mass_m')
    _string(e['terrain'], 'terrain')
    _number(e['step_height_m'], 'step_height_m', 0, 10000)
    _number(e['gravity_mps2'], 'gravity_mps2', 0.000001, 1000)
    _vector(s['position_m'], 3, 'position_m')
    q = _vector(s['orientation_xyzw'], 4, 'orientation_xyzw', -1, 1)
    if abs(sum(x*x for x in q)-1) > 1e-3:
        raise CommonFormatError('orientation_xyzwは正規化されたクォータニオンが必要です。')
    _vector(s['velocity_mps'], 3, 'velocity_mps')
    from module_network import SCENARIO_BY_KEY
    if not isinstance(sc['key'], str) or sc['key'] not in SCENARIO_BY_KEY:
        raise CommonFormatError('未対応の仮想CANシナリオです。')
    return deepcopy(config)


def default_config():
    return deepcopy(DEFAULT_CONFIG)


def config_json(config):
    return json.dumps(validate_config(config), ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def parse_config(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_FILE_BYTES:
        raise CommonFormatError('設定ファイルが大きすぎます。')
    try:
        obj = json.loads(text, parse_constant=lambda v: (_ for _ in ()).throw(CommonFormatError('NaN/Infinityは使用できません。')))
    except (ValueError, TypeError) as exc:
        raise CommonFormatError(f'JSONを読み取れません: {exc}') from exc
    return validate_config(obj)


def load_config(path):
    p = Path(path)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise CommonFormatError('設定ファイルが大きすぎます。')
    return parse_config(p.read_text(encoding='utf-8-sig'))


def save_config(path, config):
    """Write a validated config. Never auto-overwrite on app startup."""
    Path(path).write_text(config_json(config), encoding='utf-8', newline='\n')


def make_run(config, result, *, created_at=None):
    """Adapt actual virtual-CAN events, without fabricating position or velocity."""
    from module_network import Result
    cfg = validate_config(config)
    if not isinstance(result, Result) or result.scenario.key != cfg['scenario']['key']:
        raise CommonFormatError('シナリオが設定と一致しません。')
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    rows = []
    for ev in result.events:
        rows.append({
            'time_s': ev.time_ms / 1000.0,
            'position_m': None, 'orientation_xyzw': None, 'velocity_mps': None,
            'source': ev.source, 'target': ev.target,
            'message': ev.message, 'event': ev.event, 'detail': ev.detail,
        })
    return {
        'schema': RUN_SCHEMA, 'version': VERSION,
        'created_at': timestamp, 'source': 'ino.virtual_can.v8',
        'physical_parameters_applied': False,
        'limitations': '仮想CANの論理イベントのみ。位置・姿勢・速度は未計算。機体・環境パラメータはメタデータであり物理演算には反映されません。',
        'config': cfg,
        'result': {
            'evaluation': result.evaluation,
            'main_state': result.main_state, 'cam_state': result.cam_state,
            'drive_state': result.drive_state,
            'loss_count': result.loss_count, 'timeout_count': result.timeout_count,
        },
        'samples': rows,
    }


def run_json(run):
    return json.dumps(run, ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def run_csv(run):
    if run.get('schema') != RUN_SCHEMA or run.get('version') != VERSION:
        raise CommonFormatError('未対応の実行結果形式です。')
    out = io.StringIO(newline='')
    fields = ['time_s','position_x_m','position_y_m','position_z_m',
              'orientation_x','orientation_y','orientation_z','orientation_w',
              'velocity_x_mps','velocity_y_mps','velocity_z_mps',
              'source','target','message','event','detail']
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for sample in run['samples']:
        row = {'time_s': sample['time_s'], 'source': sample['source'],
               'target': sample['target'], 'message': sample['message'],
               'event': sample['event'], 'detail': sample['detail']}
        for key, names in (
            ('position_m', fields[1:4]),
            ('orientation_xyzw', fields[4:8]),
            ('velocity_mps', fields[8:11]),
        ):
            if sample[key] is not None:
                row.update(zip(names, sample[key]))
        writer.writerow(row)
    return out.getvalue()
