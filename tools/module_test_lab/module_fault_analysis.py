"""v8.3: evidence-linked explanations of *virtual* module/CAN faults.

The event log from module_network is the source of truth. This module does not
infer actual hardware faults, physical CAN behavior, or ESP32-S3 execution.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io

from module_network import Result

CAUSE_TEXT = {
    'C++拒否': ('C++制御判断', 'PC実行のC++ロジックが指令を拒否しました。判定条件とモジュール状態を確認してください。'),
    '欠落': ('仮想通信の欠落', '試験シナリオでメッセージ配送が破棄されました。送信・受信・ACKの対応関係を確認してください。'),
    'タイムアウト': ('応答タイムアウト', '設定された期限内にACKが届かなかったことを検出しました。遅延・欠落・処理拒否の可能性を切り分けてください。'),
    '異常': ('モジュール／制御異常', '仮想モデルが異常を報告しました。直前の受信・ACKと診断メッセージを確認してください。'),
}

@dataclass(frozen=True)
class AnalysisStep:
    event_index: int
    role: str  # 発端, 波及, 停止指令, 最終結果
    explanation: str


@dataclass(frozen=True)
class FaultAnalysis:
    scenario_key: str
    scenario_name: str
    evaluation: str
    classification: str
    primary_event_index: int | None
    primary_title: str
    primary_explanation: str
    root_is_observed: bool
    steps: tuple[AnalysisStep, ...]
    state_summary: str
    caution: str


def analyze_result(result: Result) -> FaultAnalysis:
    """Find the earliest logged anomaly, then trace chronological consequences.

    Important: earlier anomaly is evidence of temporal ordering, not a proof of
    physical or software causality. Ground truth is the injected virtual case.
    """
    events = result.events
    summary = (f'Main={result.main_state} / CAM={result.cam_state} / '
               f'Drive={result.drive_state} / 評価={result.evaluation}')
    caution = ('この分析は仮想通信・仮想状態とPC用C++判断のログに限ります。'
               '「停止指令送信」は実機の停止完了を意味せず、原因の因果関係も断定できません。')
    if result.evaluation == '成功':
        return FaultAnalysis(result.scenario.key, result.scenario.name,
                             result.evaluation, '異常なし', None, '異常を検出しませんでした',
                             'このシナリオでは指令・応答が期待する順序で処理されました。',
                             False, tuple(), summary, caution)
    if result.evaluation == '未判定' and result.scenario.key == 'no_landing':
        return FaultAnalysis(result.scenario.key, result.scenario.name,
                             result.evaluation, '入力なし', None, '着地入力がありません',
                             'このシナリオでは着地が入力されないため走行指令を送らず、完了を評価できません。'
                             '異常の発生を意味するものではありません。',
                             False, tuple(), summary, caution)
    first = next((i for i, e in enumerate(events) if e.event in CAUSE_TEXT), None)
    if first is None:
        return FaultAnalysis(result.scenario.key, result.scenario.name,
                             result.evaluation, '完了状態未達', None, '期待する完了状態に達していません',
                             '記録から発端を特定できません。ログの未記録イベントや状態遷移を確認してください。',
                             False, tuple(), summary, caution)
    event = events[first]
    category, explanation = CAUSE_TEXT[event.event]
    if result.scenario.key == 'slow_cam_ack' and event.event == 'タイムアウト':
        category = '仮想応答遅延／タイムアウト'
        explanation = ('この試験ではCAMのACKを意図的に遅延させています。'
                       '期限内に届かなかった事実はタイムアウトで確認できます。'
                       '送信時刻・配送時刻・待機期限を比較してください。')
    elif result.scenario.key == 'cam_reject' and event.event == '異常':
        category = '仮想CAM指令拒否'
        explanation = ('この試験ではCAMが撮影指令を拒否する設定です。'
                       'ACK受信前後のイベントからMainが異常に移った経緯を確認してください。')
    steps = [AnalysisStep(first, '発端', f'{category}：{event.detail}')]
    for i in range(first + 1, len(events)):
        e = events[i]
        if e.event in ('欠落', 'タイムアウト', '異常', '無視', 'C++拒否'):
            steps.append(AnalysisStep(i, '波及', e.detail))
        elif e.event == '送信' and e.source == 'Main' and e.target == 'Drive' and e.message.startswith('STOP('):
            steps.append(AnalysisStep(i, '停止指令', 'Mainが停止を指示しました。指令の送信とDriveの停止確認は別です。'))
        elif e.event == '評価' and e.message == 'SUMMARY':
            steps.append(AnalysisStep(i, '最終結果', e.detail))
    # Keep only logged steps; no invented states or transitions.
    return FaultAnalysis(result.scenario.key, result.scenario.name, result.evaluation,
                         category, first, f'{event.time_ms} ms：{category}',
                         explanation, True, tuple(steps), summary, caution)


def make_analysis_csv(result: Result, analysis: FaultAnalysis, *,
                      cpp_source: str = '', cpp_sha256: str = '') -> str:
    """Export all original events, annotated with evidence-linked analysis."""
    labels = {s.event_index: s for s in analysis.steps}
    out = io.StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['scenario', 'evaluation', 'classification',
                     'cpp_source', 'cpp_sha256', 'time_ms', 'source', 'target',
                     'message', 'event', 'detail', 'analysis_role', 'analysis_note',
                     'is_primary_event'])
    for idx, event in enumerate(result.events):
        step = labels.get(idx)
        writer.writerow([result.scenario.key, result.evaluation,
                         analysis.classification, cpp_source, cpp_sha256,
                         event.time_ms, event.source, event.target, event.message,
                         event.event, event.detail, step.role if step else '',
                         step.explanation if step else '',
                         '1' if idx == analysis.primary_event_index else '0'])
    return out.getvalue()
