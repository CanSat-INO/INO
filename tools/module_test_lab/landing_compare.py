"""v6: compare two trusted host C++ landing detectors using the SAME v5 test cases.

Pure comparison and evidence-bound diagnostics. No hardware, GitHub, ROS2, or
experiment ledger writes. Never claim that a particular line in C++ is causal.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import math
from pathlib import Path
from typing import Optional

from landing_batch import BatchOutcome, BatchRun, run_batch


@dataclass(frozen=True)
class Diagnosis:
    category: str
    observations: tuple[str, ...]
    checks: tuple[str, ...]
    caution: str = '原因候補です。内部のC++分岐を観測・証明したものではありません。'

    def as_text(self) -> str:
        lines = [f'【分類】{self.category}', '【観測事実】']
        lines += [f'・{s}' for s in self.observations]
        lines += ['【確認する点（仮説）】']
        lines += [f'・{s}' for s in self.checks]
        lines += [f'※ {self.caution}']
        return '\n'.join(lines)


def _seconds(value: Optional[float]) -> str:
    return '不明' if value is None else f'{value:.2f}秒'


def diagnose(outcome: BatchOutcome, tolerance_s: float) -> Diagnosis:
    """Distinguish measured facts from candidate checks; no source introspection."""
    summary = outcome.summary
    truth = summary.get('true_contact_s')
    detected = summary.get('detected_time_s')
    delay = summary.get('delay_s')
    facts = [f'評価={outcome.status}。理由: {outcome.reason}']
    if outcome.result is None:
        if outcome.status == '入力エラー':
            return Diagnosis('試験入力が不正', tuple(facts),
                             ('入力CSVの列・欠損値・数値形式を確認する。',
                              'この条件はC++判定コード自体の性能比較には含めない。'),
                             'v5の共通入力チェックの結果です。C++は実行されていません。')
        return Diagnosis('コンパイルまたは実行のエラー', tuple(facts),
                         ('C++のビルドエラー、APIの関数名と引数、実行時エラーを確認する。',
                          '信頼できるローカル.cppファイルを指定する。'))

    trace = outcome.result.log.rows
    facts.append(f'接地ラベル={_seconds(truth)} / 初回検知={_seconds(detected)} / 遅延={_seconds(delay)}')
    facts.append(f'許容遅延={tolerance_s:g}秒 / サンプル数={len(trace)}')
    facts.append(f'検知立ち上がり回数={len(outcome.result.log.rising_events)}')
    if truth is not None:
        near = [r for r in trace if r.get('imu_z_mps2') is not None and
                abs(r['time_s'] - truth) <= 0.2 + 1e-7]
        if near:
            peak = max(near, key=lambda r: abs(r['imu_z_mps2']))
            facts.append(f'接地ラベル±0.2秒のZ加速度絶対値最大={abs(peak["imu_z_mps2"]):.2f} m/s² '
                         f'（t={peak["time_s"]:.2f}秒）')
    if outcome.status == '成功':
        return Diagnosis('許容範囲内の着地検知',tuple(facts),
                         ('検知遅延と安定性を別の条件でも確認する。',
                          '機体姿勢が変わるとZ軸の値も変わる点に注意する。'),
                         '合格は仮想CSVに対する結果で、実機での動作保証ではありません。')
    if truth is None:
        return Diagnosis('正解ラベル不足',tuple(facts),
                         ('truth_contact列か実測で確認した接地時刻を追加する。',
                          '正解がない状態では成功率の判断をしない。'))
    if summary.get('starts_detected'):
        return Diagnosis('ログ開始時点で検知済み',tuple(facts),
                         ('記録を検知前から開始し、初回立ち上がりを取得する。',))
    if detected is not None and detected < truth:
        prior = [r for r in trace if r.get('imu_z_mps2') is not None and r['time_s'] < truth]
        if prior:
            strongest = max(prior, key=lambda r: abs(r['imu_z_mps2']))
            facts.append(f'接地前のZ加速度絶対値最大={abs(strongest["imu_z_mps2"]):.2f} m/s² '
                         f'（t={strongest["time_s"]:.2f}秒）。直接の原因とは限りません。')
        return Diagnosis('接地前の誤検知',tuple(facts),
                         ('接地前衝撃と検知の対応をグラフで確認する。',
                          '衝撃直後の静止判定・継続時間・気圧変化の扱いを確認する。'))
    if detected is None:
        prev_t = None
        gaps = []
        for row in trace:
            t = row['time_s']
            if prev_t is not None and prev_t < truth < t:
                gaps.append((prev_t, t))
            prev_t = t
        if gaps:
            facts.append('接地ラベル時刻をまたぐサンプル間隔: '+', '.join(f'{a:.2f}～{b:.2f}秒' for a,b in gaps))
        return Diagnosis('着地を検知できない',tuple(facts),
                         ('着地付近の加速度ピークと入力欠損を確認する。',
                          '閾値・継続時間がセンサーデータに適合しているか確認する。'))
    if delay is not None and delay > tolerance_s:
        return Diagnosis('着地検知が遅い',tuple(facts),
                         ('着地から検知までの待機時間・連続判定条件を確認する。',
                          '早期誤検知を増やさず遅延を改善できるか別条件でも検証する。'))
    return Diagnosis('判定が確定していない／その他',tuple(facts),
                     ('ログの時間範囲、正解ラベル、連続検知条件を確認する。',))


@dataclass(frozen=True)
class ComparedCase:
    key: str
    title: str
    before: BatchOutcome
    after: BatchOutcome
    change: str

    @property
    def delay_delta_s(self) -> Optional[float]:
        left, right = self.before.summary.get('delay_s'), self.after.summary.get('delay_s')
        if left is None or right is None:
            return None
        return round(right - left, 6)


def _change(before: BatchOutcome, after: BatchOutcome) -> str:
    if before.status == '失敗' and after.status == '成功':
        return '改善'
    if before.status == '成功' and after.status == '失敗':
        return '悪化'
    if before.status in ('成功', '失敗') and before.status == after.status:
        return '同判定'
    return '比較対象外'  # undetermined, invalid CSV, runtime failures never score as a regression


@dataclass(frozen=True)
class Comparison:
    before: BatchRun
    after: BatchRun
    cases: tuple[ComparedCase, ...]

    @property
    def changes(self) -> dict:
        categories = ('改善','悪化','同判定','比較対象外')
        return {c: sum(x.change == c for x in self.cases) for c in categories}

    def summary_text(self) -> str:
        a,b = self.before.counts, self.after.counts
        changes = self.changes
        return ('旧: 成功{0} / 失敗{1} / 未判定{2} / 入力エラー{3} / 実行エラー{4}   '
                '→   新: 成功{5} / 失敗{6} / 未判定{7} / 入力エラー{8} / 実行エラー{9}\n'
                '確定した合否の変化：改善{10} / 悪化{11} / 同判定{12} / 比較対象外{13}。'
                ' 未判定・入力エラーは改善/悪化に算入しません。').format(
            a['成功'],a['失敗'],a['未判定'],a['入力エラー'],a['実行エラー'],
            b['成功'],b['失敗'],b['未判定'],b['入力エラー'],b['実行エラー'],
            changes['改善'],changes['悪化'],changes['同判定'],changes['比較対象外'])


def compare_sources(before_cpp: str | Path, after_cpp: str | Path, *,
                    allowed_delay_s: float = 5.0,
                    case_keys: tuple[str,...] | None = None) -> Comparison:
    """Run both algorithms against identical deterministic input (v5 generator)."""
    if not math.isfinite(allowed_delay_s) or not 0 <= allowed_delay_s <= 600:
        raise ValueError('許容遅延は0～600秒の有限数にしてください。')
    a = run_batch(before_cpp, allowed_delay_s=allowed_delay_s, case_keys=case_keys)
    b = run_batch(after_cpp, allowed_delay_s=allowed_delay_s, case_keys=case_keys)
    map_b = {x.case.key:x for x in b.outcomes}
    cases = tuple(ComparedCase(x.case.key, x.case.title, x, map_b[x.case.key], _change(x,map_b[x.case.key]))
                  for x in a.outcomes if x.case.key in map_b)
    if len(cases) != len(a.outcomes) or len(cases) != len(b.outcomes):
        raise ValueError('片方のC++が一部条件を実行できませんでした。ビルド・実行エラーを確認してください。')
    return Comparison(a,b,cases)


def _excel_safe(value: object) -> object:
    """Protect exported CSV opened in Excel from formula injection."""
    if not isinstance(value,str):
        return value
    if value.lstrip(' \t\r\n').startswith(('=','+','-','@')):
        return "'"+value
    return value


def make_comparison_csv(comp: Comparison) -> str:
    f=io.StringIO(newline='')
    w=csv.writer(f,lineterminator='\n')
    w.writerow(['scenario_key','scenario_name','comparison','before_status','after_status',
                'true_contact_s','before_detection_s','after_detection_s',
                'before_delay_s','after_delay_s','delay_delta_s','before_reason','after_reason',
                'before_cpp','after_cpp','before_sha256','after_sha256'])
    left_source = Path(comp.before.source).name
    right_source = Path(comp.after.source).name
    def get_hash(run:BatchRun)->str:
        return next((c.result.source_sha256 for c in run.outcomes if c.result), '')
    hash_a,hash_b=get_hash(comp.before),get_hash(comp.after)
    for c in comp.cases:
        w.writerow([_excel_safe(v) for v in (
            c.key,c.title,c.change,c.before.status,c.after.status,
            c.before.summary.get('true_contact_s',c.after.summary.get('true_contact_s')),
            c.before.summary.get('detected_time_s'),c.after.summary.get('detected_time_s'),
            c.before.summary.get('delay_s'),c.after.summary.get('delay_s'),c.delay_delta_s,
            c.before.reason,c.after.reason,left_source,right_source,hash_a,hash_b)])
    return f.getvalue()
