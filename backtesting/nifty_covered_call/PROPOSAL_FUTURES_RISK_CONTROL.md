# Research Proposal: Dual-Leg Futures Risk Control & Downside Protection for NIFTY Covered Call

**Document ID:** PROP-NCC-RISK-001  
**Target Strategy:** NIFTY Covered Call (`backtesting/nifty_covered_call/` -> `strategies/scripts/nifty_covered_call_20261012110856.py`)  
**Status:** DRAFT / RESEARCH PROPOSAL (NOT DEPLOYED TO PRODUCTION)  
**Date:** 2026-10-14  
**Author:** Antigravity Quantitative Research Team

---

## 1. Problem Statement & Deficiency Analysis

The current production deployment of the NIFTY Covered Call strategy (`nifty_covered_call_20261012110856.py`) suffers from a critical structural deficiency: **it manages risk exclusively through the Short Call option leg, with zero risk constraints on the Long Futures leg**.

### Current Production Code (`evaluate_cycle`, lines 618–632):
```python
# Exit Condition 1: Profit Target (90% decay)
if curr_call_price <= pos["target_price"]:
    self.execute_exit("PROFIT_TARGET_HIT (90% Decay)", spot, curr_call_price)
    return

# Exit Condition 2: Stop Loss (3.0x initial premium)
if curr_call_price >= pos["stoploss_price"]:
    self.execute_exit("STOP_LOSS_HIT (3.0x Premium)", spot, curr_call_price)
    return

# Exit Condition 3: Roll Threshold (DTE <= roll_dte)
if dte_left <= self.roll_dte:
    self.execute_exit(f"ROLL_THRESHOLD_REACHED (DTE <= {self.roll_dte})", spot, curr_call_price)
    return
```

### The Three Structural Failure Modes:
1. **The Downside "Profit Target" Trap**:
   - In a severe market crash, the underlying index falls rapidly.
   - The short call premium decays toward zero due to delta collapse.
   - When the call drops to 90% decay (e.g. ₹8.69), **Exit Condition 1 triggers as a "PROFIT TARGET"**, liquidating BOTH legs.
   - **Result**: The strategy books a ₹5,086 profit on the call, while realizing an uncontrolled **-₹65,000 loss on the futures leg** (on a 1,000-point fall), dumping the futures at the exact bottom of the drawdown.
2. **Uncapped Crash Exposure**:
   - A covered call is structurally identical to a **synthetic short put**. The maximum premium collected on the 23100 CE is ₹86.95 (₹5,651.75).
   - Any market decline beyond 86.95 points exposes the trader to point-for-point linear loss:
     - -2.0% Index Move (-455 pts): Net loss = **-₹23,923.25**
     - -5.0% Index Move (-1,137 pts): Net loss = **-₹68,253.25**
     - -10.0% Index Move (-2,274 pts): Net loss = **-₹1,41,898.25**
3. **No Account-Level Net M2M Catastrophe Cap**:
   - If market conditions deteriorate intra-cycle, there is no dollar-value stop loss (e.g. max loss of ₹15,000 per lot).

---

## 2. Proposed Dual-Leg Risk Control Architecture

We propose introducing two complementary risk controls into the research engine:

```
                                      DUAL-LEG RISK ARCHITECTURE
                                                  │
                       ┌──────────────────────────┴──────────────────────────┐
                       ▼                                                     ▼
         LEG A: SHORT CALL DYNAMICS                            LEG B: FUTURES & NET M2M GUARDS
  ┌─────────────────────────────────────────┐               ┌─────────────────────────────────────────┐
  │ 1. 90% Premium Decay -> Take Profit    │               │ 1. Futures Trailing/Catastrophe Stop    │
  │ 2. 3.0x Premium Breach -> Call SL       │               │    (e.g., -2.0% from Entry)             │
  │ 3. DTE <= 10 Days -> Roll Trigger       │               │ 2. Max Strategy M2M Drawdown Cap        │
  │                                         │               │    (e.g., -₹20,000 per lot)             │
  └─────────────────────────────────────────┘               └─────────────────────────────────────────┘
                       │                                                     │
                       └──────────────────────────┬──────────────────────────┘
                                                  ▼
                                 Simultaneous Two-Leg Emergency Exit
                                (Avoids Naked Unhedged Options Exposure)
```

### Specific Parameter Additions:
1. `fut_stoploss_pct: float = 0.02` (2.0% maximum futures drawdown from entry price, corresponding to ~455 NIFTY points).
2. `max_drawdown_inr: float = 20000.0` (Maximum acceptable net mark-to-market loss per lot across both legs).
3. `fut_trailing_stop: bool = False` (Optional dynamic high-water-mark trail on the futures leg).

### Proposed Logic in `evaluate_cycle`:
```python
# Calculate M2M
fut_m2m = (spot - pos["fut_entry_price"]) * pos["fut_qty"]
call_m2m = (pos["call_entry_price"] - curr_call_price) * pos["call_qty"]
net_m2m = fut_m2m + call_m2m
fut_return_pct = (spot - pos["fut_entry_price"]) / pos["fut_entry_price"]

# Risk Guard 1: Futures Catastrophe Stop-Loss (-2.0%)
if fut_return_pct <= -self.fut_stoploss_pct:
    self.execute_exit(
        f"FUTURES_STOP_LOSS_HIT ({fut_return_pct*100:.2f}% <= -{self.fut_stoploss_pct*100:.1f}%)",
        spot,
        curr_call_price
    )
    return

# Risk Guard 2: Absolute Strategy Net Drawdown Cap (-₹20,000)
if net_m2m <= -self.max_drawdown_inr:
    self.execute_exit(
        f"MAX_NET_DRAWDOWN_BREACHED (M2M: ₹{net_m2m:,.2f} <= -₹{self.max_drawdown_inr:,.2f})",
        spot,
        curr_call_price
    )
    return

# Risk Guard 3: Call Profit Target (Only if Futures leg is NOT in severe drawdown)
if curr_call_price <= pos["target_price"]:
    # Guard: If futures has lost more than the entire call premium, do not classify as profit target
    reason = "PROFIT_TARGET_HIT (90% Decay)" if net_m2m > 0 else "BEARISH_DECAY_CLOSE (Net Negative)"
    self.execute_exit(reason, spot, curr_call_price)
    return

# Risk Guard 4: Call Stop Loss (3.0x premium on rapid rally)
if curr_call_price >= pos["stoploss_price"]:
    self.execute_exit("CALL_STOP_LOSS_HIT (3.0x Premium)", spot, curr_call_price)
    return

# Risk Guard 5: Monthly Roll Threshold (DTE <= 10)
if dte_left <= self.roll_dte:
    self.execute_exit(f"ROLL_THRESHOLD_REACHED (DTE <= {self.roll_dte})", spot, curr_call_price)
    return
```

---

## 3. Comparative Stress Test Matrix (Per 1 Lot / 65 Qty)

| Market Scenario | Spot Move | Current Production Net P&L | Proposed Architecture Net P&L | Loss Prevention Benefit |
| :--- | :---: | :---: | :---: | :---: |
| **Normal Bullish Drift (+2%)** | +455 pts | **+₹29,129.75** (Capped) | **+₹29,129.75** (Capped) | No change (Preserves edge) |
| **Moderate Pullback (-1%)** | -227 pts | -₹9,103.25 | -₹9,103.25 | Within buffer |
| **Sharp Correction (-3%)** | -682 pts | -₹38,678.25 | **-₹20,000.00** (Net M2M Cap) | **+₹18,678.25 saved** |
| **Severe Drop (-5%)** | -1,137 pts | -₹68,253.25 | **-₹20,000.00** (Cut at SL) | **+₹48,253.25 saved** |
| **Crash / Shock (-10%)** | -2,274 pts | -₹1,41,898.25 | **-₹20,000.00** (Cut at SL) | **+₹1,21,898.25 saved** |

---

## 4. Next Steps & Governance Review Requirement
1. Validate proposed logic in `backtesting/nifty_covered_call/test_futures_risk_control.py`.
2. Run historical Monte Carlo stress tests across 2020 (COVID shock) and 2024 election gaps.
3. Keep current AWS deployment strictly in read-only observation mode until formal review sign-off.
