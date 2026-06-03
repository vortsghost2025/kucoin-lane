# Mega Sweep Results — Reference Index

> **CRITICAL FINDING**: 1h timeframe has ZERO edge. 1d timeframe has massive edge.

| Timeframe | Fee Level | Profitable Combos | % Profitable | Best Net Return | File |
|-----------|-----------|-------------------|--------------|-----------------|------|
| 1h | taker (0.1%) | 0 / 32,256 | 0.0% | 0.0% | mega_sweep_1h_taker.json |
| 4h | taker (0.1%) | 546 / 30,744 | 2.0% | +8.47% | mega_sweep_4h_taker.json |
| 4h | maker (0.05%) | 1,365 / 30,744 | 5.1% | +16.17% | mega_sweep_4h_maker.json |
| 1d | taker (0.1%) | 18,097 / 32,256 | 78.9% | +69.88% | mega_sweep_1d_taker.json |
| 1d | maker (0.05%) | 19,015 / 32,256 | 82.9% | +83.00% | mega_sweep_1d_maker.json |

## Key Takeaways

- **1d Vol Breakout**: 100% of configs profitable, PF=2.02-2.23, best at ATR_mult=1.0
- **1d Supertrend**: 98% profitable, conservative +31.70% maker, DD=3.1%
- **4h EMA21/200**: Only profitable 4h strategy, range-dependent (bull trades LOSE)
- **1h UNTRADABLE**: Zero profitable combos at any risk level — fees + noise destroy all edge

## Detailed Reports

- [4H Taker Report](MEGA_SWEEP_4H_TAKER.md)
- [4H Maker Report](MEGA_SWEEP_4H_MAKER.md)
- [1D Taker Report](MEGA_SWEEP_1D_TAKER.md)
- [1D Maker Report](MEGA_SWEEP_1D_MAKER.md)
- [Cross-Timeframe Analysis](CROSS_TIMEFRAME_ANALYSIS.md)

## Decision

**Switch to 1d timeframe + Vol Breakout strategy** — implemented as of journal entry 32.