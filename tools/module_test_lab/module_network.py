"""Deterministic v8.1 *logical* Main/CAM/Drive + CAN message simulator.

This is NOT a physical CAN implementation, does not implement arbitration,
actual CAN IDs, electrical faults or actual ESP32 firmware.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import heapq
import io
from typing import Callable

BUS_DELAY_MS = 10
ACK_TIMEOUT_MS = 200
FINAL_TIME_MS = 2200

@dataclass(frozen=True)
class Scenario:
    key: str
    name: str
    description: str

SCENARIOS = (
    Scenario('normal', '正常なモジュール連携', '着地入力→Drive走行指令→CAM撮影指令→Drive停止までACKを確認します。'),
    Scenario('drop_drive_cmd', 'Drive走行指令の欠落', 'Mainの走行指令がDriveに届かなかった場合を確認します。'),
    Scenario('drop_drive_ack', 'Drive応答の欠落', '走行指令は届いたのに応答だけ失われる場合を確認します。'),
    Scenario('drop_cam_ack', 'CAM応答の欠落', 'CAMへの撮影指令の応答だけが失われる場合を確認します。'),
    Scenario('slow_cam_ack', 'CAM応答の遅延', 'CAMの応答がタイムアウト後に届く場合を確認します。'),
    Scenario('cam_reject', 'CAM指令の拒否', 'CAMが撮影指令を受け付けられなかった場合を確認します。'),
    Scenario('drop_stop_ack', 'Drive停止応答の欠落', '停止指令は届くが、そのACKが欠落する場合を確認します。'),
    Scenario('no_landing', '着地入力なし', '着地が確認されない場合、移動指令を出さないことを確認します。'),
)
SCENARIO_BY_KEY = {x.key: x for x in SCENARIOS}

@dataclass(frozen=True)
class Event:
    time_ms: int
    source: str
    target: str
    message: str
    event: str
    detail: str

@dataclass(frozen=True)
class Result:
    scenario: Scenario
    evaluation: str
    main_state: str
    cam_state: str
    drive_state: str
    events: tuple[Event, ...]
    diagnostics: tuple[str, ...]

    @property
    def loss_count(self) -> int:
        return sum(e.event == '欠落' for e in self.events)

    @property
    def timeout_count(self) -> int:
        return sum(e.event == 'タイムアウト' for e in self.events)


def simulate(key: str) -> Result:
    """Run one virtual scenario with deterministic ordering and finite events."""
    if key not in SCENARIO_BY_KEY:
        raise ValueError(f'不明なシナリオ: {key}')
    scenario = SCENARIO_BY_KEY[key]
    state = {'Main': 'WAIT_LANDING', 'CAM': 'IDLE', 'Drive': 'IDLE'}
    diagnostics = []
    events = []
    timeline = []
    counter = 0
    next_id = 0
    clock = 0
    pending = {}  # id => (command, expected_module)

    def record(source: str, target: str, message: str, event: str, detail: str):
        events.append(Event(clock, source, target, message, event, detail))

    def schedule(at: int, fn: Callable[[], None]):
        nonlocal counter
        if at < clock or at > 5000:
            raise RuntimeError('イベント時刻が不正です。')
        counter += 1
        heapq.heappush(timeline, (at, counter, fn))

    def fault(reason: str):
        if state['Main'] == 'FAULT':
            return
        state['Main'] = 'FAULT'
        diagnostics.append(reason)
        record('Main', 'ALL', 'FAULT', '異常', reason)
        # Send a virtual stop command even if acknowledgement/command was lost.
        send('Main', 'Drive', 'STOP', require_ack=False)
        diagnostics.append('Mainは異常を記録してDriveへ停止指令を送信しました。')

    def timeout(message_id: int):
        if message_id not in pending:
            return
        command, target = pending.pop(message_id)
        record('Main', target, command, 'タイムアウト',
               f'指令ID={message_id}: {ACK_TIMEOUT_MS} ms以内にACKを受信できませんでした。')
        fault(f'{target}の{command}応答が{ACK_TIMEOUT_MS} ms以内に届きませんでした。通信・処理状況の確認が必要です。')

    def send(source: str, target: str, command: str, *, require_ack: bool=True,
             reply_to: int=0, accepted: bool=True):
        nonlocal next_id
        next_id += 1
        message_id = next_id
        is_ack = command == 'ACK'
        short = f'ACK({reply_to})' if is_ack else f'{command}({message_id})'
        record(source, target, short, '送信', '仮想CANメッセージを送信しました。')
        if require_ack:
            pending[message_id] = (command, target)
            schedule(clock+ACK_TIMEOUT_MS, lambda mid=message_id: timeout(mid))
        should_drop = (
            (key == 'drop_drive_cmd' and source == 'Main' and command == 'MOVE') or
            (key == 'drop_drive_ack' and source == 'Drive' and is_ack and reply_to == 1) or
            (key == 'drop_cam_ack' and source == 'CAM' and is_ack) or
            (key == 'drop_stop_ack' and source == 'Drive' and is_ack and
             pending.get(reply_to, ('', ''))[0] == 'STOP')
        )
        if should_drop:
            record(source, target, short, '欠落', '仮想故障条件により配送を破棄しました。')
            return
        delay = BUS_DELAY_MS
        if key == 'slow_cam_ack' and source == 'CAM' and is_ack:
            delay += ACK_TIMEOUT_MS + 70
        schedule(clock+delay, lambda: deliver(source,target,command,message_id,reply_to,accepted))

    def deliver(source: str, target: str, command: str, message_id: int,
                reply_to: int, accepted: bool):
        short = f'ACK({reply_to})' if command == 'ACK' else f'{command}({message_id})'
        record(source, target, short, '受信', 'メッセージを配送しました。')
        if target == 'Main':
            if command != 'ACK':
                fault('Mainが未定義のメッセージを受信しました。')
                return
            expected = pending.get(reply_to)
            if not expected or expected[1] != source:
                record('Main', source, short, '無視', '対応する待機中の指令がありません。遅延ACKなどの可能性があります。')
                return
            orig_command, _ = pending.pop(reply_to)
            if not accepted:
                fault(f'{source}が{orig_command}指令を拒否しました。モジュール側の状態や処理を確認してください。')
                return
            if state['Main'] == 'FAULT':
                record('Main', source, short, '無視', 'MainはFAULTのため、新たな動作を開始しません。')
                return
            if orig_command == 'MOVE':
                state['Main'] = 'WAIT_CAM'
                send('Main','CAM','CAPTURE')
            elif orig_command == 'CAPTURE':
                state['Main'] = 'WAIT_STOP'
                send('Main','Drive','STOP')
            elif orig_command == 'STOP':
                state['Main'] = 'FINISHED'
            return
        if target == 'Drive':
            if command == 'MOVE':
                state['Drive'] = 'MOVING'
                send('Drive','Main','ACK',require_ack=False,reply_to=message_id)
            elif command == 'STOP':
                state['Drive'] = 'STOPPED'
                send('Drive','Main','ACK',require_ack=False,reply_to=message_id)
            else:
                fault(f'Driveが想定外の指令{command}を受信しました。')
            return
        if target == 'CAM':
            if command == 'CAPTURE':
                ok = key != 'cam_reject'
                state['CAM'] = 'DONE' if ok else 'FAULT'
                send('CAM','Main','ACK',require_ack=False,reply_to=message_id,accepted=ok)
            else:
                fault(f'CAMが想定外の指令{command}を受信しました。')
            return
        raise RuntimeError('不明な宛先です。')

    record('System', 'ALL', 'INIT', '開始', '仮想モジュールと仮想CANバスを初期化しました。')
    if key != 'no_landing':
        def on_landing():
            state['Main'] = 'WAIT_DRIVE'
            record('Sensor', 'Main', 'LANDING', '入力', '仮想着地イベントを受信しました。')
            send('Main', 'Drive', 'MOVE')
        schedule(1000, on_landing)
    for _ in range(100):
        if not timeline:
            break
        clock, _, action = heapq.heappop(timeline)
        action()
    else:
        raise RuntimeError('イベント上限を超えました。')
    clock = max(clock, FINAL_TIME_MS)
    if state['Main'] == 'FINISHED' and state['Drive'] == 'STOPPED' and state['CAM'] == 'DONE':
        evaluation = '成功'
        diagnostics.append('全指令の応答が期限内に到達し、Mainは完了、Driveは停止状態です。')
    elif key == 'no_landing' and state['Main'] == 'WAIT_LANDING' and state['Drive'] == 'IDLE':
        evaluation = '未判定'
        diagnostics.append('着地入力がないため走行指令は送信されませんでした。ミッション完了は評価できません。')
    else:
        evaluation = '失敗'
        if not diagnostics:
            diagnostics.append('期待する完了状態に到達できませんでした。状態遷移を確認してください。')
    record('System', 'ALL', 'SUMMARY', '評価',
           f'{evaluation}: Main={state["Main"]}, CAM={state["CAM"]}, Drive={state["Drive"]}')
    return Result(scenario, evaluation, state['Main'], state['CAM'],
                  state['Drive'], tuple(events), tuple(diagnostics))


def make_log_csv(result: Result) -> str:
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['scenario','time_ms','source','target','message','event','detail'])
    for e in result.events:
        writer.writerow([result.scenario.key,e.time_ms,e.source,e.target,e.message,e.event,e.detail])
    return out.getvalue()
