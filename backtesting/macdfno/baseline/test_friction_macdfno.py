import sys
from pathlib import Path
sys.path.insert(0, '/Users/mac/Desktop/openalgo/backtesting/macdfno/baseline')
import test_macd_universe_and_runners as t

frictions = [0.05, 0.07, 0.10, 0.12, 0.15]

print("=== Friction Stress Test: Variant G (Asymmetric Universe + Pure MACD Cross) ===")
for f in frictions:
    n, net, pf, mdd, pf26 = t.test_engine_variant(
        long_tp=0.0, short_tp=0.0, trail_pct=0.35, conservative_trailing=True, use_asym_universe=True, friction_pct=f
    )
    print(f"Friction {f:.2f}%: Net={net:>7.2f}%, PF={pf:>6.3f}, MDD={mdd:>6.2f}%, 2026_PF={pf26:>6.3f}")

print("\n=== Friction Stress Test: Variant E (Asymmetric Universe + 0.35% Runner) ===")
for f in frictions:
    n, net, pf, mdd, pf26 = t.test_engine_variant(
        long_tp=3.0, short_tp=1.5, trail_pct=0.35, conservative_trailing=True, use_asym_universe=True, friction_pct=f
    )
    print(f"Friction {f:.2f}%: Net={net:>7.2f}%, PF={pf:>6.3f}, MDD={mdd:>6.2f}%, 2026_PF={pf26:>6.3f}")
