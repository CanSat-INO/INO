"""Command-line preview of deterministic landing cases (no ledger writes)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cpp_landing_runner import DEMO_SOURCE, BASE
from landing_batch import run_batch, make_summary_csv

source = BASE/'cpp_landing'/'shared_landing'/'host_adapter.cpp'
if not source.exists():
    source=DEMO_SOURCE
report = run_batch(source)
print('使用したC++:', source)
for item in report.outcomes:
    delay=item.summary.get('delay_s')
    print(f'{item.case.title}: {item.status} / 遅延={"—" if delay is None else f"{delay:.2f}秒"}')
print('合計:', report.counts)
print('これは仮想サンプルです。実機検証ではありません。')
