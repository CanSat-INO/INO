"""Deterministic *toy* phase-transition checks for CanSat Module Test Lab.

No hardware, imported firmware, ROS 2, Gazebo, GNSS position simulation, or physical
motion accuracy is claimed. Distances and sensor signals are synthetic test values.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import csv
import io
import json
import math
from pathlib import Path


MODES = {
    'full': 'ミッション通し',
    'landing': '着地判定のみ',
    'gnss': 'GNSS測位のみ',
    'gps': 'GPS誘導のみ',
    'camera': 'カメラ誘導のみ',
}
SCENARIOS = {
    'normal': '正常ケース（仮想）',
    'landing_rejected': '着地判定不成立',
    'gnss_timeout': 'GNSS測位タイムアウト',
    'camera_missing': '赤色目標が見つからない',
    'obstacle': '障害物検知による停止',
    'emergency': '緊急停止入力',
}
PHASES = {
    'LANDING_WAIT': '着地待機',
    'GNSS_WAIT': 'GNSS測位待機',
    'GPS_GUIDANCE': 'GPS誘導',
    'CAM_SEARCH': 'カメラ探索',
    'CAM_APPROACH': 'カメラ接近',
    'DONE': '完了',
    'STOPPED': '停止',
}
CSV_FIELDS = ('time_s', 'phase', 'phase_ja', 'distance_m', 'impact_mps2',
              'gyro_dps', 'gnss_fixed', 'target_visible', 'red_ratio',
              'command', 'event')


@dataclass(frozen=True)
class PhaseConfig:
    time_step_s: float = 0.5
    max_time_s: float = 90.0
    landing_impact_mps2: float = 18.0
    landing_gyro_dps: float = 2.0
    stable_ms: int = 800
    gnss_fix_delay_s: float = 3.0
    gnss_timeout_s: float = 15.0
    gps_start_distance_m: float = 12.0
    gps_speed_mps: float = 1.0
    cam_detection_delay_s: float = 2.0
    cam_search_timeout_s: float = 12.0
    cam_speed_mps: float = 0.5
    obstacle_after_s: float = -1.0
    emergency_after_s: float = -1.0


@dataclass(frozen=True)
class PhaseResult:
    mode: str
    scenario: str
    config: PhaseConfig
    status: str
    reason: str
    rows: tuple[dict, ...]
    transitions: tuple[dict, ...]

    @property
    def duration_s(self) -> float:
        return float(self.rows[-1]['time_s']) if self.rows else 0.0


def configuration(mode: str, scenario: str, **overrides) -> PhaseConfig:
    if mode not in MODES:
        raise ValueError('未知の試験モードです。')
    if scenario not in SCENARIOS:
        raise ValueError('未知のケースです。')
    base = PhaseConfig()
    scenario_changes = {
        'normal': {},
        'landing_rejected': {'landing_impact_mps2': 10.0},
        'gnss_timeout': {'gnss_fix_delay_s': 22.0},
        'camera_missing': {'cam_detection_delay_s': 20.0},
        'obstacle': {'obstacle_after_s': 9.0},
        'emergency': {'emergency_after_s': 5.0},
    }
    conf = replace(base, **scenario_changes[scenario])
    if overrides:
        conf = replace(conf, **overrides)
    validate_config(conf)
    return conf


def validate_config(conf: PhaseConfig) -> None:
    for key, value in asdict(conf).items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f'不正な数値です: {key}')
    if not (0.1 <= conf.time_step_s <= 2.0):
        raise ValueError('時間刻みは0.1～2秒で指定してください。')
    if not (5.0 <= conf.max_time_s <= 180.0):
        raise ValueError('最大試験時間は5～180秒で指定してください。')
    if not (0 <= conf.landing_impact_mps2 <= 150 and 0 <= conf.landing_gyro_dps <= 360):
        raise ValueError('着地センサー値の範囲外です。')
    if not (0 <= conf.stable_ms <= 10000):
        raise ValueError('安定時間の範囲外です。')
    if not (0 <= conf.gnss_fix_delay_s <= 180 and 0.5 <= conf.gnss_timeout_s <= 180):
        raise ValueError('GNSS設定の範囲外です。')
    if not (0.5 <= conf.gps_start_distance_m <= 500 and 0.1 <= conf.gps_speed_mps <= 10):
        raise ValueError('GPS距離・仮想速度の範囲外です。')
    if not (0 <= conf.cam_detection_delay_s <= 180 and 0.5 <= conf.cam_search_timeout_s <= 180):
        raise ValueError('カメラ検出時間の範囲外です。')
    if not (0.1 <= conf.cam_speed_mps <= 10):
        raise ValueError('カメラ仮想速度の範囲外です。')
    for v in (conf.obstacle_after_s, conf.emergency_after_s):
        if not (-1 <= v <= 180):
            raise ValueError('障害物・緊急停止時刻の範囲外です。')


def run_phase_test(mode: str, scenario: str = 'normal', conf: PhaseConfig | None = None) -> PhaseResult:
    if mode not in MODES or scenario not in SCENARIOS:
        raise ValueError('モードまたはケースが不正です。')
    conf = conf or configuration(mode, scenario)
    validate_config(conf)
    first = {'full': 'LANDING_WAIT', 'landing': 'LANDING_WAIT',
             'gnss': 'GNSS_WAIT', 'gps': 'GPS_GUIDANCE', 'camera': 'CAM_SEARCH'}[mode]
    phase = first
    phase_entered = 0.0
    distance = min(conf.gps_start_distance_m, 3.0) if mode == 'camera' else conf.gps_start_distance_m
    rows: list[dict] = []
    transitions: list[dict] = [{'time_s': 0.0, 'phase': phase, 'reason': '試験開始'}]
    status = 'TIMEOUT'
    reason = '制限時間内に終了しませんでした。'
    target_visible = False
    gnss_fixed = mode in ('gps', 'camera')  # isolated stages assume previous stages succeeded

    def transition(new_phase: str, t: float, why: str):
        nonlocal phase, phase_entered
        if phase != new_phase:
            phase = new_phase
            phase_entered = t
            transitions.append({'time_s': round(t, 3), 'phase': phase, 'reason': why})

    count = int(conf.max_time_s / conf.time_step_s) + 1
    for i in range(count):
        t = round(i * conf.time_step_s, 3)
        if t > conf.max_time_s + 1e-9:
            break
        elapsed = t - phase_entered
        event = ''
        command = '停止'
        if conf.emergency_after_s >= 0 and t >= conf.emergency_after_s:
            status, reason = 'STOPPED', '仮想緊急停止入力'
            transition('STOPPED', t, reason)
            event = reason
        elif conf.obstacle_after_s >= 0 and t >= conf.obstacle_after_s and phase in ('GPS_GUIDANCE', 'CAM_APPROACH'):
            status, reason = 'STOPPED', '仮想障害物を検知'
            transition('STOPPED', t, reason)
            event = reason
        elif phase == 'LANDING_WAIT':
            if t >= 2.0:
                okay = (conf.landing_impact_mps2 >= 15.0 and
                        conf.landing_gyro_dps <= 5.0 and conf.stable_ms >= 600)
                if okay:
                    if mode == 'landing':
                        status, reason = 'PASS', '着地判定の仮想条件を満たしました。'
                        transition('DONE', t, reason)
                    else:
                        transition('GNSS_WAIT', t, '仮想着地判定が成立')
                    event = transitions[-1]['reason']
                else:
                    status, reason = 'STOPPED', '仮想着地判定の条件を満たしません。'
                    transition('STOPPED', t, reason)
                    event = reason
        elif phase == 'GNSS_WAIT':
            if elapsed >= conf.gnss_fix_delay_s:
                gnss_fixed = True
                if mode == 'gnss':
                    status, reason = 'PASS', '仮想GNSS測位成立'
                    transition('DONE', t, reason)
                else:
                    transition('GPS_GUIDANCE', t, '仮想GNSS測位成立')
                event = transitions[-1]['reason']
            elif elapsed >= conf.gnss_timeout_s:
                status, reason = 'STOPPED', 'GNSS測位が仮想制限時間を超過'
                transition('STOPPED', t, reason)
                event = reason
        elif phase == 'GPS_GUIDANCE':
            command = 'GPS誘導（仮想）'
            if elapsed > 0:
                distance = max(0.0, distance - conf.gps_speed_mps * conf.time_step_s)
            if distance <= 3.0 + 1e-9:
                if mode == 'gps':
                    status, reason = 'PASS', '仮想カメラ切替距離に到達'
                    transition('DONE', t, reason)
                else:
                    transition('CAM_SEARCH', t, '仮想カメラ誘導へ切替')
                event = transitions[-1]['reason']
                command = '停止'
        elif phase == 'CAM_SEARCH':
            command = '探索（仮想）'
            if elapsed >= conf.cam_detection_delay_s:
                target_visible = True
                transition('CAM_APPROACH', t, '仮想目標を検出')
                event = transitions[-1]['reason']
            elif elapsed >= conf.cam_search_timeout_s:
                status, reason = 'STOPPED', '仮想目標の探索タイムアウト'
                transition('STOPPED', t, reason)
                event = reason
                command = '停止'
        elif phase == 'CAM_APPROACH':
            command = 'カメラ接近（仮想）'
            target_visible = True
            distance = max(0, distance - conf.cam_speed_mps * conf.time_step_s)
            red = min(1.0, max(0.0, 0.15 + (3.0 - distance) * 0.25))
            if distance <= 0.5 and red >= 0.5:
                status, reason = 'PASS', '仮想目標への接近条件が成立'
                transition('DONE', t, reason)
                event = reason
                command = '停止'
        red_ratio = (round(min(1.0, max(0.0, 0.15 + (3.0 - distance) * .25)), 4)
                     if target_visible else 0.0)
        row = {
            'time_s': t, 'phase': phase, 'phase_ja': PHASES[phase],
            'distance_m': round(distance, 3),
            'impact_mps2': conf.landing_impact_mps2 if t == 2.0 or (t >= 2 and i > 0 and (i-1)*conf.time_step_s < 2) else 0.0,
            'gyro_dps': conf.landing_gyro_dps if t >= 2.0 and t < 2.0 + conf.time_step_s else 0.0,
            'gnss_fixed': int(gnss_fixed), 'target_visible': int(target_visible),
            'red_ratio': red_ratio, 'command': command, 'event': event,
        }
        rows.append(row)
        if phase in ('DONE', 'STOPPED'):
            break
    if phase not in ('DONE', 'STOPPED'):
        transitions.append({'time_s': rows[-1]['time_s'], 'phase': 'STOPPED',
                            'reason': reason})
        rows[-1]['phase'] = 'STOPPED'
        rows[-1]['phase_ja'] = PHASES['STOPPED']
        rows[-1]['event'] = reason
        rows[-1]['command'] = '停止'
    return PhaseResult(mode, scenario, conf, status, reason, tuple(rows), tuple(transitions))


def result_document(result: PhaseResult) -> dict:
    config_dict = asdict(result.config)
    signature = sha256(json.dumps({'mode': result.mode, 'scenario': result.scenario,
                                    'config': config_dict}, sort_keys=True,
                                   ensure_ascii=False).encode('utf-8')).hexdigest()
    return {'schema_version': 'v17-virtual-phase-1',
            'simulation_only': True, 'mode': result.mode, 'scenario': result.scenario,
            'status': result.status, 'reason': result.reason,
            'duration_s': result.duration_s, 'config_sha256': signature,
            'config': config_dict, 'transitions': list(result.transitions),
            'samples': list(result.rows)}


def csv_text(result: PhaseResult) -> str:
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(result.rows)
    return output.getvalue()


def save_csv(result: PhaseResult, path: str | Path) -> None:
    Path(path).write_text(csv_text(result), encoding='utf-8-sig')


def save_json(result: PhaseResult, path: str | Path) -> None:
    Path(path).write_text(json.dumps(result_document(result), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
