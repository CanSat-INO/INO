"""Read-only summaries of verified v6/v7 report attachments (not time traces)."""
from __future__ import annotations

import csv
import math
from io import StringIO


def _rank_key(row: dict) -> tuple[int, int]:
    """Sort v7 summaries by their stored rank; keep invalid ranks at the end."""
    raw = str(row.get('rank') or '').strip()
    try:
        n = int(raw)
        if n > 0:
            return (0, n)
    except ValueError:
        pass
    return (1, 0)


def _cell(row: dict, key: str) -> str:
    """Format display text only. Never alter the original CSV or numeric evaluation."""
    value = str(row.get(key) or '').replace('\n', ' ').strip()[:90]
    if not value:
        return '—'
    if key in ('impact_threshold_mps2', 'hold_ms',
               'mean_success_delay_s', 'delay_s',
               'before_delay_s', 'after_delay_s'):
        try:
            n = float(value)
            if math.isfinite(n):
                if key in ('impact_threshold_mps2', 'hold_ms'):
                    return f'{n:g}'
                return f'{n:.2f}'
        except ValueError:
            pass
    return value


def parse_report_csv(content: bytes, name: str) -> dict | None:
    """Return report view for recognized schema; otherwise None for time-series parser."""
    reader = csv.DictReader(StringIO(content.decode('utf-8-sig')))
    fields = set(reader.fieldnames or ())
    if {'scenario_key', 'before_status', 'after_status', 'comparison'} <= fields:
        kind = 'v6 C++コード比較レポート'
        columns = (('scenario_key', '条件'), ('before_status', '旧判定'),
                   ('after_status', '新判定'), ('comparison', '変化'),
                   ('before_delay_s', '旧遅延(s)'), ('after_delay_s', '新遅延(s)'))
    elif {'impact_threshold_mps2', 'hold_ms', 'success', 'failure', 'rank'} <= fields:
        kind = 'v7 パラメータ探索レポート'
        columns = (('rank', '順位'), ('impact_threshold_mps2', '閾値(m/s²)'),
                   ('hold_ms', '静止(ms)'), ('success', '成功'), ('failure', '失敗'),
                   ('early_false_detections', '早期誤検知'),
                   ('mean_success_delay_s', '平均遅延(s)'))
    elif {'impact_threshold_mps2', 'hold_ms', 'scenario_key', 'status'} <= fields:
        kind = 'v7 条件別判定レポート'
        columns = (('impact_threshold_mps2', '閾値'), ('hold_ms', '静止(ms)'),
                   ('scenario_key', '条件'), ('status', '判定'), ('delay_s', '遅延(s)'))
    else:
        return None

    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) > 10000:
            raise ValueError('レポート行数が上限を超えています。')
    if kind == 'v7 パラメータ探索レポート':
        rows.sort(key=_rank_key)

    lines = [kind, f'添付ファイル：{name}',
             '※ レポートCSVは時系列センサーログではありません。', '']
    lines.append(' | '.join(label for _, label in columns))
    lines.append('-' * 70)
    for row in rows[:128]:
        lines.append(' | '.join(_cell(row, key) for key, _ in columns))
    if len(rows) > 128:
        lines.append(f'... ほか{len(rows) - 128}行（CSVファイルをご確認ください）')
    if not rows:
        lines.append('レポートに結果行がありません。')
    return {'trace': [],
            'message': f'{kind}（{len(rows)}行）。時系列グラフの代わりに「比較・最適化レポート」タブを確認してください。',
            'report_text': '\n'.join(lines), 'filename': name}
