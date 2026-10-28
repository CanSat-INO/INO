"""Deterministic offline Main/CAM/Drive message-contract exercise.

Only toy packet delivery, ACK, TTL and watchdog behavior. This is NOT a CAN,
TWELITE, ROS 2, radio, driver, motor or safety simulation. No side effects.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import csv
import heapq
import io
import json
import math

SCENARIOS = {
    'normal': '正常な仮想通信',
    'drop_drive_ack': 'Drive応答（ACK）欠損',
    'drop_cam_target': 'CAM検出通知の欠損',
    'duplicate_cmd': 'Drive指令の重複受信',
    'delay_drive_ack': 'Drive応答の大幅遅延',
    'stale_cam_target': '古いCAM検出通知',
    'emergency': '緊急停止メッセージ',
}
NODES = frozenset(('Main', 'CAM', 'Drive'))
CONTRACT = {
    ('Main', 'Drive', 'DRIVE_CMD'),
    ('Drive', 'Main', 'DRIVE_ACK'),
    ('CAM', 'Main', 'CAM_TARGET'),
    ('CAM', 'Main', 'EMERGENCY'),
}
EXPORT_FIELDS = ('time_s', 'src', 'dst', 'kind', 'seq', 'state', 'detail')


@dataclass(frozen=True)
class BusConfig:
    latency_s: float = .10
    ack_timeout_s: float = .80
    target_deadline_s: float = 17.50
    max_age_s: float = 1.00


@dataclass(frozen=True)
class BusResult:
    scenario: str
    config: BusConfig
    status: str
    reason: str
    events: tuple[dict, ...]
    delivered: int
    dropped: int
    duplicates: int
    pending_ack: int
    final_time_s: float


def validate_config(c: BusConfig):
    values = asdict(c)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v)
           for v in values.values()):
        raise ValueError('仮想通信の設定は有限な数値で指定してください。')
    if not (0.01 <= c.latency_s <= 1.5):
        raise ValueError('通信遅延は0.01～1.5秒にしてください。')
    if not (.1 <= c.ack_timeout_s <= 5.0):
        raise ValueError('ACK待機時間は0.1～5秒にしてください。')
    if not (16.5 <= c.target_deadline_s <= 20.0):
        raise ValueError('CAM通知の期限は16.5～20秒にしてください。')
    if not (.1 <= c.max_age_s <= 10.0):
        raise ValueError('鮮度の有効期限は0.1～10秒にしてください。')


def validate_packet(src: str, dst: str, kind: str, seq: int, created_s: float):
    if (src, dst, kind) not in CONTRACT:
        raise ValueError(f'許可されていない通信です: {src} → {dst} / {kind}')
    if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
        raise ValueError('メッセージ番号は正の整数です。')
    if not isinstance(created_s, (int, float)) or not math.isfinite(created_s) or created_s < 0:
        raise ValueError('生成時刻が不正です。')


def run_bus_test(scenario: str = 'normal', config: BusConfig | None = None) -> BusResult:
    if scenario not in SCENARIOS:
        raise ValueError('不明な仮想通信シナリオです。')
    c = config or BusConfig()
    validate_config(c)
    events: list[dict] = []
    heap: list[tuple[float, int, dict]] = []
    serial = 0
    seq_counter = 0
    delivered = dropped = duplicates = 0
    pending: dict[int, float] = {}
    drive_seen: set[int] = set()
    cam_received = False
    status = 'RUNNING'
    reason = ''
    result_time = 22.0

    def log(t, src, dst, kind, seq, state, detail):
        events.append({'time_s': round(t, 2), 'src': src, 'dst': dst,
                       'kind': kind, 'seq': seq, 'state': state, 'detail': detail})

    def send(t, src, dst, kind, payload='', *, seq=None, created_at=None, duplicate=False):
        nonlocal seq_counter, serial, dropped
        if seq is None:
            seq_counter += 1
            seq = seq_counter
        created = t if created_at is None else created_at
        validate_packet(src, dst, kind, seq, created)
        packet = dict(src=src, dst=dst, kind=kind, seq=seq, payload=payload, created_s=created)
        log(t, src, dst, kind, seq, '送信', str(payload))
        if scenario == 'drop_drive_ack' and kind == 'DRIVE_ACK' and payload == 'GPS_FORWARD':
            dropped += 1
            log(t, src, dst, kind, seq, '破棄', '仮想ACK欠損')
            return seq
        if scenario == 'drop_cam_target' and kind == 'CAM_TARGET':
            dropped += 1
            log(t, src, dst, kind, seq, '破棄', '仮想CAM通知欠損')
            return seq
        delay = c.latency_s
        if scenario == 'delay_drive_ack' and kind == 'DRIVE_ACK' and payload == 'GPS_FORWARD':
            delay += 1.50
        serial += 1
        heapq.heappush(heap, (round(t + delay, 4), serial, packet))
        if kind == 'DRIVE_CMD' and not duplicate:
            pending[seq] = round(t + c.ack_timeout_s, 4)
        return seq

    # Each row is a synthetic *input* event; not firmware or real sensor output.
    plans = [
        (0.0, 'Main', 'Drive', 'DRIVE_CMD', 'STOP'),
        (2.0, 'Main', 'Drive', 'DRIVE_CMD', 'HOLD'),
        (5.0, 'Main', 'Drive', 'DRIVE_CMD', 'GPS_FORWARD'),
        (14.0, 'Main', 'Drive', 'DRIVE_CMD', 'HOLD'),
        (16.0, 'CAM', 'Main', 'CAM_TARGET', 'red_target=true'),
        (16.3, 'Main', 'Drive', 'DRIVE_CMD', 'CAM_APPROACH'),
        (21.0, 'Main', 'Drive', 'DRIVE_CMD', 'STOP'),
    ]
    if scenario == 'emergency':
        plans.append((9.0, 'CAM', 'Main', 'EMERGENCY', 'virtual_alert=true'))
    plans.sort()
    next_plan = 0

    def process_packet(t: float, packet: dict):
        nonlocal delivered, duplicates, cam_received, status, reason
        src, dst, kind, seq = (packet[k] for k in ('src', 'dst', 'kind', 'seq'))
        if t - packet['created_s'] > c.max_age_s + 1e-8:
            log(t, src, dst, kind, seq, '拒否', '期限切れ（鮮度チェック）')
            return
        if kind == 'DRIVE_CMD':
            if seq in drive_seen:
                duplicates += 1
                log(t, src, dst, kind, seq, '重複除外', 'Driveで二重実行を防止')
                return
            drive_seen.add(seq)
            delivered += 1
            log(t, src, dst, kind, seq, '受信', packet['payload'])
            send(t, 'Drive', 'Main', 'DRIVE_ACK', packet['payload'], seq=seq)
        elif kind == 'DRIVE_ACK':
            delivered += 1
            pending.pop(seq, None)
            log(t, src, dst, kind, seq, '受信', 'ACK確認: ' + packet['payload'])
        elif kind == 'CAM_TARGET':
            delivered += 1
            cam_received = True
            log(t, src, dst, kind, seq, '受信', 'CAM検出通知')
        elif kind == 'EMERGENCY':
            delivered += 1
            log(t, src, dst, kind, seq, '受信', '仮想緊急停止要求')
            status, reason = 'STOPPED', '緊急停止要求を受信（仮想）'
            # Do not assert motor stopped; this test has no actual actuator.
            send(t, 'Main', 'Drive', 'DRIVE_CMD', 'STOP')

    # Tick-based scheduler for predictable and reproducible ordering.
    for tick in range(221):
        t = round(tick / 10, 2)
        if status != 'RUNNING':
            break
        while next_plan < len(plans) and plans[next_plan][0] <= t + 1e-7:
            at, src, dst, kind, payload = plans[next_plan]
            next_plan += 1
            if kind == 'DRIVE_CMD' and payload == 'CAM_APPROACH' and not cam_received:
                log(t, src, dst, kind, 0, '保留', 'CAM通知なし：接近指令は送らない')
                continue
            created_at = 10.0 if scenario == 'stale_cam_target' and kind == 'CAM_TARGET' else None
            seq = send(t, src, dst, kind, payload, created_at=created_at)
            if scenario == 'duplicate_cmd' and kind == 'DRIVE_CMD' and payload == 'GPS_FORWARD':
                send(t, src, dst, kind, payload, seq=seq, duplicate=True)
        while heap and heap[0][0] <= t + 1e-7:
            _, _, packet = heapq.heappop(heap)
            process_packet(t, packet)
            if status != 'RUNNING':
                break
        if status != 'RUNNING':
            result_time = t
            break
        expired = [seq for seq, deadline in pending.items() if deadline <= t + 1e-7]
        if expired:
            status, reason = 'STOPPED', f'Drive応答期限超過（seq={expired[0]}）'
            log(t, 'Main', 'Drive', 'WATCHDOG', expired[0], '停止判定', reason)
            result_time = t
            break
        if t >= c.target_deadline_s and not cam_received:
            status, reason = 'STOPPED', 'CAM検出通知が期限までに到着しませんでした。'
            log(t, 'Main', 'CAM', 'WATCHDOG', 0, '停止判定', reason)
            result_time = t
            break
        if t == 22.0:
            if not pending and cam_received:
                status, reason = 'PASS', '仮想メッセージとACKの受信条件を満たしました。'
            else:
                status, reason = 'STOPPED', '未確認のメッセージがあります。'
            result_time = t
            log(t, 'Main', '-', 'RESULT', 0, status, reason)

    return BusResult(scenario, c, status, reason, tuple(events), delivered, dropped,
                     duplicates, len(pending), result_time)


def csv_text(result: BusResult) -> str:
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    writer.writerows(result.events)
    return stream.getvalue()


def json_text(result: BusResult) -> str:
    obj = {'schema': 'cansat.virtual_bus.v18', 'scenario': result.scenario,
           'config': asdict(result.config), 'status': result.status,
           'reason': result.reason, 'final_time_s': result.final_time_s,
           'delivered': result.delivered, 'dropped': result.dropped,
           'duplicates': result.duplicates, 'pending_ack': result.pending_ack,
           'events': result.events, 'disclaimer': 'OFFLINE SYNTHETIC, NOT DEVICE OR SAFETY TEST'}
    data = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)
    return data + '\n'


def scenario_signature(result: BusResult) -> str:
    return sha256(json_text(result).encode('utf-8')).hexdigest()
