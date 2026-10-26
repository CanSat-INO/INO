"""Run with: cd tools/module_test_lab && python examples/run_landing_optimizer_demo.py"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from landing_optimizer import DEMO_TUNABLE,optimize
result=optimize(DEMO_TUNABLE,(12.0,14.0,18.0),(0.0,300.0,700.0))
for rank, candidate in enumerate(result.ranked,1):
    print(rank,'threshold',candidate.threshold,'hold ms',candidate.hold_ms,
          'success',candidate.counts['成功'],'false early',candidate.false_early,
          'avg delay',candidate.mean_delay_s)
