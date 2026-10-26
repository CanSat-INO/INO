"""v7 parameter sweep on trusted, opt-in host C++ exposing landing_configure().

Compile one temporary binary; run each candidate in an isolated process. Reuse
v5 synthetic cases and v4 CSV judgement without modifying ordinary v4-v6 APIs.
This is *grid search*, not proof of a globally optimal or hardware-safe value.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import itertools
import math
from pathlib import Path
import tempfile
from typing import Callable

from arduino_csv import MAX_CSV_BYTES, analyze, parse_csv_text
from cpp_landing_runner import API, CppResult, _run, read_sensor_csv
from landing_batch import BatchOutcome, CASES, CASES_BY_KEY, make_case_csv
from landing_compare import diagnose, _excel_safe

BASE = Path(__file__).resolve().parent
RUNNER = BASE/'cpp_landing'/'runner_parameterized.cpp'
DEMO_TUNABLE = BASE/'cpp_landing'/'example_detector_tunable.cpp'
MAX_COMBINATIONS = 16


def parse_values(text: str, *, name: str, minimum: float, maximum: float) -> tuple[float,...]:
    pieces = text.split(',')
    if not 1 <= len(pieces) <= 16 or any(not p.strip() for p in pieces):
        raise ValueError(f'{name}はカンマ区切りで1～16個入力してください。')
    values = []
    for piece in pieces:
        try:
            n = float(piece.strip())
        except ValueError as exc:
            raise ValueError(f'{name}に数値以外が含まれています。') from exc
        if not math.isfinite(n) or not minimum <= n <= maximum:
            raise ValueError(f'{name}は{minimum:g}～{maximum:g}の有限数にしてください。')
        if n in values: raise ValueError(f'{name}に重複があります。')
        values.append(n)
    return tuple(values)


@dataclass(frozen=True)
class Candidate:
    threshold: float
    hold_ms: float
    outcomes: tuple[BatchOutcome,...]

    @property
    def counts(self):
        return {key: sum(o.status==key for o in self.outcomes)
                for key in ('成功','失敗','未判定','入力エラー','実行エラー')}

    @property
    def false_early(self):
        return sum(o.status=='失敗' and o.summary.get('detected_time_s') is not None and
                   o.summary.get('true_contact_s') is not None and
                   o.summary['detected_time_s'] < o.summary['true_contact_s'] for o in self.outcomes)

    @property
    def mean_delay_s(self):
        values=[o.summary.get('delay_s') for o in self.outcomes if o.status=='成功'
                and o.summary.get('delay_s') is not None]
        return sum(values)/len(values) if values else None

    @property
    def eligible(self):
        return all(o.status!='実行エラー' for o in self.outcomes) and len(self.outcomes)==len(CASES)

    @property
    def sort_key(self):
        # Explicit: maximize valid successes, penalize early false detection, minimize delay.
        if not self.eligible: return (1,0,0,math.inf,self.threshold,self.hold_ms)
        return (0,-self.counts['成功'],self.false_early,
                self.mean_delay_s if self.mean_delay_s is not None else math.inf,
                self.threshold,self.hold_ms)


@dataclass(frozen=True)
class Optimization:
    source: str
    source_sha256: str
    tolerance_s: float
    candidates: tuple[Candidate,...]

    @property
    def ranked(self):
        return tuple(sorted(self.candidates,key=lambda c:c.sort_key))

    @property
    def best(self):
        winner=self.ranked[0] if self.candidates else None
        return winner if winner and winner.eligible else None


def _evaluate(program: Path, source: Path, source_hash: str, key: str,
              threshold: float, hold_ms: float, tolerance_s:float, temp:Path) -> BatchOutcome:
    case=CASES_BY_KEY[key]
    contents=make_case_csv(key)
    input_file=temp/(key+'.csv')
    input_file.write_text(contents,encoding='utf-8')
    try:
        sensor=read_sensor_csv(input_file)
    except ValueError as exc:
        # Only intentionally malformed case should fail during parsing.
        status='入力エラー' if key=='invalid_imu' else '実行エラー'
        return BatchOutcome(case,contents,None,status,str(exc))
    if key=='invalid_imu':
        return BatchOutcome(case,contents,None,'実行エラー','不正入力が検証を通過しました。')
    input_lines=''.join(
        f"{r['time_ms']:.10g},{r['imu_z_mps2']:.16g},"
        f"{(-1.0 if r['pressure_pa'] is None else r['pressure_pa']):.16g}\n"
        for r in sensor.rows)
    try:
        flags=_run([str(program),f'{threshold:.15g}',f'{hold_ms:.15g}'],
                   input_text=input_lines,timeout=10,label='v7 C++判定処理').splitlines()
        if len(flags)!=len(sensor.rows) or any(f not in ('0','1') for f in flags):
            raise ValueError('C++出力が不正です。各入力行に0/1を1行ずつ返してください。')
        f=io.StringIO(newline=''); writer=csv.writer(f,lineterminator='\n')
        has_truth=any(r['truth_contact'] is not None for r in sensor.rows)
        header=['time_ms','imu_z_mps2','pressure_pa','landing_detected']
        if has_truth: header.append('truth_contact')
        writer.writerow(header)
        for r,flag in zip(sensor.rows,flags):
            row=[f"{r['time_ms']:.10g}",f"{r['imu_z_mps2']:.16g}",
                 '' if r['pressure_pa'] is None else f"{r['pressure_pa']:.16g}",flag]
            if has_truth: row.append(int(bool(r['truth_contact'])))
            writer.writerow(row)
        csv_text=f.getvalue()
        if len(csv_text.encode('utf-8'))>MAX_CSV_BYTES:
            raise ValueError('生成ログが900KiBを超えました。')
        log=parse_csv_text(csv_text,source_name='v7_parameterized_output.csv')
        report=analyze(log,expected_time_s=None,allowed_delay_s=tolerance_s)
        result=CppResult(csv_text,report,log,source_hash,source.name,sensor.original_name)
        return BatchOutcome(case,contents,result,report['status'],report['reason'])
    except (OSError,ValueError) as exc:
        return BatchOutcome(case,contents,None,'実行エラー',str(exc))


def optimize(source_path: str|Path, thresholds: tuple[float,...], holds_ms: tuple[float,...],
             *, allowed_delay_s:float=5.0,
             progress:Callable[[int,int],None]|None=None) -> Optimization:
    source=Path(source_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower()!='.cpp' or not 0<source.stat().st_size<=100*1024:
        raise ValueError('100KiB以下の信頼できるローカル.cppを選択してください。')
    if not math.isfinite(allowed_delay_s) or not 0<=allowed_delay_s<=600:
        raise ValueError('許容遅延は0～600秒にしてください。')
    if not thresholds or not holds_ms or len(thresholds)*len(holds_ms)>MAX_COMBINATIONS:
        raise ValueError('組み合わせは1～16通りにしてください。')
    for name,values,low,high in (('加速度閾値',thresholds,1,100),('静止継続時間',holds_ms,0,5000)):
        if len(set(values))!=len(values) or any(not math.isfinite(x) or not low<=x<=high for x in values):
            raise ValueError(f'{name}の値が不正または重複しています。')
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='cansat-v7-opt-') as td:
        temp=Path(td); program=temp/'parameter_runner'
        _run(['g++','-std=c++17','-O1','-Wall','-Wextra','-I',str(API.parent),
              str(RUNNER),str(source),'-o',str(program)],
             timeout=25,label='v7 C++コンパイル（landing_configure対応が必要）')
        candidates=[]
        total=len(thresholds)*len(holds_ms)
        for threshold,hold in itertools.product(thresholds,holds_ms):
            outcomes=tuple(_evaluate(program,source,sha,case.key,threshold,hold,
                                     allowed_delay_s,temp) for case in CASES)
            candidates.append(Candidate(threshold,hold,outcomes))
            if progress: progress(len(candidates),total)
    return Optimization(str(source),sha,allowed_delay_s,tuple(candidates))


def make_optimization_csv(optimization:Optimization)->str:
    f=io.StringIO(newline=''); w=csv.writer(f,lineterminator='\n')
    w.writerow(['impact_threshold_mps2','hold_ms','success','failure','undetermined',
                'input_error','runtime_error','early_false_detections','mean_success_delay_s',
                'rank','source_cpp','source_sha256'])
    rankings={id(c):i for i,c in enumerate(optimization.ranked,1)}
    for c in optimization.candidates:
        counts=c.counts
        w.writerow([_excel_safe(x) for x in (
            c.threshold,c.hold_ms,counts['成功'],counts['失敗'],counts['未判定'],
            counts['入力エラー'],counts['実行エラー'],c.false_early,c.mean_delay_s,
            rankings[id(c)],Path(optimization.source).name,optimization.source_sha256)])
    return f.getvalue()


def make_optimization_cases_csv(optimization:Optimization)->str:
    f=io.StringIO(newline='');w=csv.writer(f,lineterminator='\n')
    w.writerow(['impact_threshold_mps2','hold_ms','scenario_key','scenario_name',
                'status','contact_s','detected_s','delay_s','reason'])
    for c in optimization.candidates:
        for o in c.outcomes:
            w.writerow([_excel_safe(x) for x in (c.threshold,c.hold_ms,o.case.key,
                o.case.title,o.status,o.summary.get('true_contact_s'),
                o.summary.get('detected_time_s'),o.summary.get('delay_s'),o.reason)])
    return f.getvalue()
