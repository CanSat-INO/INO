"""Run the v6 sample comparison without launching a GUI."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))

from cpp_landing_runner import DEMO_SOURCE
from landing_compare import compare_sources,diagnose


def main():
    newer=DEMO_SOURCE.with_name('example_detector_v2.cpp')
    report=compare_sources(DEMO_SOURCE,newer)
    print(report.summary_text())
    print('')
    for case in report.cases:
        print(f'{case.title}: {case.before.status} → {case.after.status} [{case.change}]')
    print('\n=== 着地前の衝撃: 旧コードの診断 ===')
    example=next(c for c in report.cases if c.key=='early_shock')
    print(diagnose(example.before,report.before.tolerance_s).as_text())


if __name__=='__main__':
    main()
