# AGY MASTER SOP — AUTO-APPROVE STRATEGY RESEARCH & GOVERNANCE

This is a PERMANENT governance rule for this research environment.

It applies to:

* All existing strategies
* All new strategies
* Covered Call (NIFTYBEES + NIFTY CE)
* EMA + MACD Confluence
* MACD
* Ichimoku
* RSI
* Momentum
* Mean Reversion
* Options strategies
* Futures strategies
* Equity strategies
* Every current and future NFO strategy
* Any future strategy created or researched by AGY

The objective is to make the research process **automated, reproducible, controlled and auditable**, while preventing unvalidated strategies from reaching execution.

---

# 1. MASTER DIRECTORY RULE

The existing directory:

```text
~/backtesting/
```

is the MASTER RESEARCH DIRECTORY.

DO NOT create another `backtesting` directory.

Every new strategy MUST have its own dedicated subdirectory:

```text
~/backtesting/<strategy_name>/
```

Example:

```text
~/backtesting/
├── covered call/
├── macd/
├── ichimoku/
├── oi strategy/
├── emabackcrossopen/
└── <future strategy>/
```

Never mix files from different strategies.

---

# 2. AUTOMATIC NEW-STRATEGY INITIALIZATION

When a new strategy is introduced, AGY should automatically:

1. Identify the strategy name.
2. Create:

```text
~/backtesting/<strategy_name>/
```

3. Create an appropriate research structure.
4. Create the initial README.
5. Create the strategy specification.
6. Register the strategy in the research lifecycle.
7. Begin Phase 1 automatically.

Do NOT wait for separate approval merely to create the research folder or begin routine research.

---

# 3. STANDARD STRATEGY DIRECTORY

Unless a strategy requires a justified alternative structure, use:

```text
~/backtesting/<strategy_name>/
│
├── README.md
├── strategy_spec.md
│
├── data/
│   └── nfo_contract_manifest/    (Mandatory for NFO strategies)
├── baseline/
├── research/
├── validation/
├── forward/
└── reports/
```

All strategy-specific files must remain inside this directory.

---

# 3A. IDENTICAL DIGITAL-TWIN TESTING PATTERN & STATE ISOLATION RULE

Following the proven **NIFTY Covered Call** governance pattern:

1. **Parity Requirement:**
   - Every live production strategy in `strategies/liveonopenalgo/<name>.py` must maintain an **identical digital-twin runner** inside its dedicated backtesting folder: `backtesting/<name>/<name>.py`.
   - The digital-twin script in `backtesting/` must share identical logic, indicators, confirmation windows, risk exits (targets/catastrophe stops), order pacing delays, and database retry routines as live.

2. **Mandatory State & Log Isolation (Zero Contamination):**
   - The digital-twin script in `backtesting/` must strictly resolve its state file relative to its own folder (`SCRIPT_DIR / "<name>_state.json"` or via `--state-file`).
   - Running tests, simulation harnesses, or forward-validations in `backtesting/` **must NEVER read, write, reset, or mutate** production state files in `strategies/liveonopenalgo/` (e.g. `macdfno_state.json`, `emacrossopen_state.json`).

3. **Pre-Promotion Regression Assertion:**
   - Before any strategy logic modification or parameter update is promoted from `backtesting/` to `strategies/liveonopenalgo/`, it must achieve a **100% pass rate** on its built-in assertion suite (e.g. `python3 <script> --test`).


---

# 4. AUTO-APPROVAL PRINCIPLE

AGY is authorized to automatically proceed through routine RESEARCH phases when:

* The work remains inside `~/backtesting/<strategy_name>/`.
* Routine NFO contract verification and manifest maintenance are being conducted.
* No unrelated project is modified.
* No execution code is deployed.
* No live trading is initiated.
* Required validation gates pass.
* No material safety or data-integrity issue is detected.

The user does NOT need to manually approve every routine research phase or monthly NFO contract verification.

---

# 5. MASTER RESEARCH WORKFLOW

The permanent research workflow is:

```text
NEW STRATEGY
      ↓
AUTO CREATE ~/backtesting/<strategy_name>/
      ↓
PHASE 1 — RESEARCH
      ↓ AUTO
PHASE 2 — DATA VALIDATION
      ↓ AUTO
PHASE 3 — MECHANICAL BASELINE
      ↓ AUTO
PHASE 4 — CONTROLLED RESEARCH
      ↓ AUTO
PHASE 5 — OOS / WALK-FORWARD
      ↓ AUTO
PHASE 6 — ROBUSTNESS
      ↓ AUTO
PHASE 7 — STRATEGY FREEZE
      ↓
      ═══ USER APPROVAL ═══
      ↓
FORWARD / PAPER TEST
      ↓
      ═══ USER APPROVAL ═══
      ↓
OPENALGO / EXECUTION
      ↓
      ═══ USER APPROVAL ═══
      ↓
LIVE TRADING
```

For NFO strategies, insert into the recurring lifecycle:

```text
LAST TRADING WEEK OF EVERY MONTH
              ↓
NFO CONTRACT VERIFICATION
              ↓
CHANGE DETECTION
              ↓
CONTRACT VALIDATION
              ↓
NEXT MONTHLY CYCLE
```

AGY must not skip phases.

---

# 6. PHASE 1 — RESEARCH & SPECIFICATION

Automatically:

* Study the strategy mechanics.
* Define the research hypothesis.
* Define entry rules.
* Define exit rules.
* Define position sizing.
* Define risk management.
* Define assumptions.
* Identify data requirements.
* Identify market-specific rules.
* Identify potential biases.
* Define baseline methodology.

Do not claim profitability.
Do not optimize.

---

# 7. PHASE 2 — DATA ACQUISITION & VALIDATION

Automatically:

* Identify appropriate data sources.
* Acquire data where permitted and available.
* Validate completeness.
* Validate timestamps.
* Validate contracts.
* Validate corporate actions.
* Validate expiry information.
* Validate lot sizes.
* Check survivorship bias.
* Check look-ahead bias.
* Check duplicate records.
* Check invalid prices.
* Generate a data audit.

If the data is inadequate:

```text
STOP — DATA QUALITY FAILURE
```

Do not continue to backtesting.

---

# 8. PHASE 3 — MECHANICAL BASELINE

Automatically build and run a transparent baseline after Phase 2 passes.

The baseline must be:

* Mechanical
* Reproducible
* Non-optimized
* Auditable

Compare against an appropriate benchmark.
Do not optimize the baseline.

---

# 8A. CERTIFIED MOMENTUM & DUAL-CONFIRMATION BASELINE STANDARD (OCTOBER 2026 UPDATE)

Following the empirical audit across 166,444 bars (33 F&O instruments, 2023–2026), the classical "unfiltered whole-universe" baseline has been proven mathematically invalid (yielding -59.63% Net P&L due to chop in mean-reverting underlyings).

Effective immediately, the **New Approved Baseline** for dual-confirmation momentum strategies (specifically **`emacrossopen.py`** and related derivatives) is defined as:

### 1. The Certified Baseline Architecture (`Candidate EXP_I`)
* **Core Universe Restriction (`EXP_B` Edge):** Entries are strictly restricted to verified persistent trend leaders:
  * `TOP_LONGS`: `SUNPHARMA`, `BAJAJ-AUTO`, `BPCL`, `WIPRO`, `TATASTEEL`, `BAJFINANCE`, `NTPC`
  * `TOP_SHORTS`: `SUNPHARMA`, `BAJAJ-AUTO`, `M&M`, `BPCL`, `NTPC`, `NIFTY`
  * *Uncurated symbols must not be entered.*
* **1H Macro Trend Regime Guard:** 
  * Long entries require bar `Close > EMA26`.
  * Short entries require bar `Close < EMA26`.
* **Lookahead-Free Conservative Trailing Runner:**
  * Fixed Target Banking: +3.00% Long / +1.50% Short.
  * Trailing Distance: 0.35% from High Water Mark (HWM).
  * Lookahead-Free Accounting: Same-candle trail breach must never be ignored; runners are tracked on subsequent bars.
  * Catastrophe Stop-Loss: -6.00% emergency stop.
* **Empirical Baseline Benchmark Metrics:**
  * **Net P&L:** +233.34% (380 trades)
  * **Profit Factor:** 1.817 (In-Sample: 1.788 | Out-of-Sample: 1.860 | 2026 Holdout: 1.820)
  * **Max Drawdown:** 16.78% (vs 175.3% on old raw basket)
  * **Friction Resilience:** Remains robust up to 0.15% round-trip drag (Net +202.94%, PF 1.685).

### 2. Strategy Target Confirmation
* **Primary Target for Optimization & Digital-Twin Alignment:**  
  * **Research Digital-Twin:** `backtesting/emacrossopen/emacrossopen.py`
  * **Live Production Candidate (Post-Paper Simulation Approval):** `strategies/liveonopenalgo/emacrossopen.py`
* **Rule for `macdfno.py`:**  
  * `macdfno.py` is a single-indicator histogram momentum strategy and must NOT inherit dual-confirmation rules without its own independent Phase 3 baseline audit.

---

# 9. PHASE 4 — CONTROLLED RESEARCH

After the baseline has been validated, AGY may automatically conduct controlled experiments.

Examples:

* Parameter sensitivity
* Entry timing
* Exit timing
* Strike selection
* Stop loss
* Target
* Position sizing
* Volatility filters
* Trend filters
* Regime filters

Every experiment MUST have:

```text
Experiment ID
Hypothesis
Parameters
Dataset
Method
Result
Interpretation
Conclusion
```

Never overwrite previous experiments.

---

# 10. OPTIMIZATION GOVERNANCE

Optimization is allowed only after a valid baseline exists.

Do NOT optimize blindly.

Use:

* Parameter bounds
* Controlled search
* Experiment logging
* In-sample separation
* Out-of-sample validation
* Walk-forward testing
* Robustness analysis

Do not select a strategy solely because it has the highest historical return.

---

# 11. OUT-OF-SAMPLE VALIDATION

OOS validation is mandatory.

The OOS dataset must not influence parameter selection.
Do not repeatedly optimize against the OOS period.

If OOS performance materially deteriorates:

```text
STOP — OOS FAILURE
```

or return to research with a clearly documented new experiment.

---

# 12. WALK-FORWARD VALIDATION

Where applicable, conduct walk-forward testing.

Document:

* Training window
* Validation window
* Test window
* Re-optimization frequency
* Parameters selected
* OOS results

Avoid using future information.

---

# 13. ROBUSTNESS TESTING

Automatically test robustness where applicable:

* Parameter perturbation
* Slippage sensitivity
* Transaction-cost sensitivity
* Different market regimes
* Different volatility regimes
* Different periods
* Monte Carlo / trade-order analysis where appropriate

The strategy should demonstrate that its edge is not dependent on one extremely precise parameter combination.

---

# 14. STRATEGY FREEZE

After successful OOS, walk-forward and robustness validation, AGY may automatically prepare:

```text
STRATEGY-FROZEN
```

documentation.

The frozen package must contain:

* Final rules
* Final parameters
* Data period
* OOS results
* Walk-forward results
* Robustness results
* Cost assumptions
* Known limitations
* Version
* Reproducibility information

However:

**FREEZE ≠ LIVE APPROVAL**

---

# 15. PERMANENT NFO STRATEGY GOVERNANCE & CONTRACT VERIFICATION

The following rules are permanent and apply to **every current and future NFO strategy**.

## 15.1 NFO CONTRACT VERIFICATION — PERMANENT RULE

For every strategy using NSE F&O (NFO) instruments, AGY MUST verify the applicable NFO contract list during the **last trading week of every month**.

This verification must be completed before the next monthly strategy cycle is initialized.

This applies to:

* NIFTY
* BANKNIFTY
* FINNIFTY
* MIDCPNIFTY
* Stock F&O
* Futures
* Options
* Any other NFO instrument used by a strategy

## 15.2 AUTHORITATIVE SOURCE

Use the most authoritative available source for NFO contract specifications.

Prefer:

1. NSE official contract information/circulars
2. Official exchange contract files
3. Verified broker contract/master data where exchange data is unavailable

Do not rely on an old static contract list.
Do not invent contract symbols or specifications.

## 15.3 MONTHLY VERIFICATION ITEMS

For every relevant NFO contract, verify:

* Underlying
* Instrument type
* Trading symbol
* Expiry date
* Weekly expiry availability
* Monthly expiry availability
* Strike interval
* Available strikes
* Lot size
* Contract multiplier
* Contract status
* Effective date
* Settlement type
* Expiry-day rules
* Any newly introduced contracts
* Any expired/removed contracts
* Exchange circular changes

## 15.4 MONTHLY NFO MANIFEST

Each NFO-based strategy must maintain:

```text
~/backtesting/<strategy_name>/data/nfo_contract_manifest/
```

Create a monthly version:

```text
nfo_contract_manifest_YYYY_MM.md
```

Never destroy historical manifests.

Each manifest must contain:

```text
Verification Date
Data Source
Underlying
Instrument Type
Symbol
Expiry
Lot Size
Strike Interval
Settlement Type
Contract Status
Effective Date
Changes From Previous Month
Verification Result
```

## 15.5 CHANGE DETECTION

Compare the current month's NFO manifest against the previous verified manifest.

If anything changes, generate:

```text
NFO CONTRACT CHANGE DETECTED
```

and report:

```text
Underlying:
Contract:
Previous Specification:
New Specification:
Effective Date:
Reason/Source:
Impact on Strategy:
Impact on Backtest:
Required Action:
```

## 15.6 HISTORICAL BACKTEST PROTECTION

IMPORTANT:

**Never apply the current NFO contract list retrospectively.**

For historical backtesting, determine the contract specification applicable on the actual historical date.

The mapping must follow:

```text
Historical Trade Date
        ↓
Historical Exchange Specification
        ↓
Historical Contract
        ↓
Historical Lot Size
        ↓
Historical Expiry
        ↓
Historical Strike Rules
```

This rule is mandatory for all NFO strategies.

## 15.7 FUTURE CONTRACT PROTECTION

Do not assume that a future expiry, lot size, strike interval, or contract symbol exists merely because it exists today.

Future contracts must be validated against the latest available official exchange information.

If future contract information cannot be verified:

```text
STOP — FUTURE NFO CONTRACT NOT VERIFIED
```

Do not fabricate the missing information.

## 15.8 COVERED CALL — SPECIFIC REQUIREMENT

For the current:

**NIFTYBEES + NIFTY CE Covered Call**

strategy, before every monthly cycle verify:

### NIFTY

* Monthly CE expiry
* Applicable lot size
* Available strikes
* Strike interval
* Contract symbol
* Settlement rules
* Contract listing/trading status

### NIFTYBEES

* ETF remains tradable
* Correct security symbol
* Corporate-action adjustments
* Any split/bonus/dividend-related adjustment relevant to the backtest

The NIFTYBEES position does not expire, but the NIFTY CE contract does.

## 15.9 NFO AUTO-APPROVAL SCOPE

Routine NFO verification is covered by the existing **AUTO-APPROVE RESEARCH** policy.

AGY may automatically:

* Check NFO specifications
* Update the monthly manifest
* Compare against the previous manifest
* Update historical contract mappings
* Perform data validation
* Continue the research workflow

No manual approval is required for routine verification.

## 15.10 NFO HARD STOP CONDITIONS

AGY MUST STOP if:

* NFO contract specification is contradictory
* Lot size cannot be verified
* Expiry cannot be verified
* Contract symbol cannot be verified
* Historical contract mapping is ambiguous
* Exchange data conflicts with broker data and cannot be resolved
* A material change affects a frozen strategy
* The strategy would require changing approved live execution logic
* Future NFO contract cannot be verified

Report:

```text
STOP CONDITION TRIGGERED

Reason:
Evidence:
Affected Strategy:
Affected Contract:
Affected Files:
Recommended Action:
```

## 15.11 NO AUTOMATIC LIVE CHANGES

The NFO monthly verification process must NOT automatically:

* Modify live trading logic
* Modify production strategy files
* Deploy new code
* Change broker orders
* Place trades
* Change live position sizing

The verification is a **research/data governance process**.

Live execution remains behind the existing explicit user approval gate.

## 15.12 NFO DIRECTORY GOVERNANCE

All NFO research artifacts must remain inside:

```text
~/backtesting/<strategy_name>/
```

Do NOT place research files in:

```text
~/strategy/
```

`~/strategy/` remains the **approved execution directory only**.

## 15.13 EXISTING STRATEGIES PROTECTION

Do not modify existing working strategies merely because the Master SOP has changed.

For existing strategies:

* Preserve current execution code.
* Preserve existing configuration.
* Apply the new NFO verification rule to future research/backtesting work.
* Any production modification requires explicit user approval.

## 15.14 MONTHLY VERIFICATION REPORT

After each monthly verification, provide a concise report:

```text
NFO MONTHLY VERIFICATION

Month:
Verification Date:

Contracts Checked:
Changes Detected:
Lot-Size Changes:
Expiry Changes:
Strike Changes:
New Contracts:
Expired Contracts:

Affected Strategies:

Data Integrity:
PASS / FAIL

Research Continuation:
AUTHORIZED / STOPPED
```

---

# 16. AUTOMATIC STOP CONDITIONS

AGY MUST STOP automatically if any of the following occurs:

### Data

* Data unavailable
* Material missing data
* Incorrect contract history
* Unresolved corporate-action issue
* Suspicious data
* Survivorship bias
* Look-ahead bias

### NFO & Derivatives Governance

* NFO contract specification is contradictory
* Lot size cannot be verified
* Expiry cannot be verified
* Contract symbol cannot be verified
* Historical contract mapping is ambiguous
* Exchange data conflicts with broker data and cannot be resolved
* A material change affects a frozen strategy
* The strategy would require changing approved live execution logic
* Future contract cannot be verified (`STOP — FUTURE NFO CONTRACT NOT VERIFIED`)

### Research

* Baseline cannot reproduce
* Equity curve does not reconcile
* Trade ledger does not reconcile
* Material accounting mismatch
* OOS failure
* Walk-forward failure
* Robustness failure

### Governance

* Attempt to modify unrelated strategy
* Attempt to write outside the strategy research directory
* Attempt to modify `~/strategy/` without authorization
* Attempt to deploy execution code without authorization

When stopping, clearly state:

```text
STOP CONDITION TRIGGERED
Reason:
Evidence:
Affected Strategy:
Affected Contract:
Affected Files:
Recommended Action:
```

---

# 17. FILE CHANGE CONTROL

Before every material change, maintain a change record.

Report:

* Created
* Modified
* Deleted
* Moved

For each:

* File path
* Reason
* Phase
* Impact

Never silently modify unrelated files.

---

# 18. EXPERIMENT VERSIONING

Every experiment must be uniquely identifiable.

Recommended:

```text
STRAT-001
STRAT-001-BL
STRAT-001-R01
STRAT-001-R02
STRAT-001-OOS
STRAT-001-WF
STRAT-001-ROB
STRAT-001-FROZEN
```

Never overwrite historical research results.

---

# 19. REPRODUCIBILITY

Every final research result must be reproducible from:

* Strategy version
* Code version
* Dataset version
* Configuration
* Parameters
* Costs
* Slippage
* Execution assumptions

Record these in the research report.

---

# 20. PERFORMANCE REPORTING

Every completed baseline/research strategy should report, where applicable:

* Initial capital
* Final capital
* Total return
* CAGR
* Maximum drawdown
* Drawdown duration
* Sharpe
* Sortino
* Calmar
* Win rate
* Profit factor
* Average trade
* Median trade
* Best trade
* Worst trade
* Annual returns
* Monthly returns
* Transaction costs
* Slippage
* Turnover
* Capital utilization

Compare against a relevant benchmark.

---

# 21. HARD EXECUTION GATE

The following actions ALWAYS require explicit user approval:

### Moving/copying strategy into:

```text
~/strategy/
```

### Creating production execution code

### Connecting the strategy to OpenAlgo

### Connecting to a broker

### Paper trading

### Live trading

### Sending real orders

### Changing an approved live strategy

AGY must never automatically perform these actions.

---

# 22. `~/strategy/` GOVERNANCE

Treat:

```text
~/strategy/
```

as:

**APPROVED EXECUTION ONLY**

It must NOT be used for:

* Early research
* Experimental code
* Unvalidated strategies
* Optimization
* Data analysis
* Temporary scripts

Research belongs in:

```text
~/backtesting/<strategy_name>/
```

Execution belongs in:

```text
~/strategy/
```

---

# 23. EXISTING STRATEGIES

Do not restructure or migrate existing strategies automatically.

For existing projects:

* Preserve current files.
* Do not rename unnecessarily.
* Do not move files without explicit instruction.
* Do not alter working execution code merely to conform to this SOP.

This SOP governs future research unless a separate migration is explicitly approved.

---

# 24. USER REPORTING

At the completion of every phase, provide a concise report containing:

```text
PHASE
STATUS
FILES CREATED
FILES MODIFIED
DATA USED
TESTS PERFORMED
KEY RESULTS
VALIDATION STATUS
STOP CONDITIONS
NEXT PHASE
```

If the phase passed and auto-approval criteria are satisfied:

```text
AUTO-APPROVED → PROCEEDING TO NEXT RESEARCH PHASE
```

If a hard gate is reached:

```text
HARD APPROVAL REQUIRED
```

---

# 25. NO FALSE CONFIDENCE

Never describe a strategy as:

* Guaranteed
* Proven profitable
* Risk-free
* Market-proof
* Institutional-grade

unless the evidence genuinely supports the exact claim.

Clearly distinguish:

**Observed historical result**

from:

**Research conclusion**

from:

**Forward expectation**

---

# 26. FINAL GOVERNANCE PRINCIPLE

AGY has **research autonomy** but does not have **capital-deployment authority**.

Routine research and NFO verification:

**AUTO-APPROVED**

Strategy deployment, production modification, broker connection and live trading:

**EXPLICIT USER APPROVAL REQUIRED**

Historical contract specifications:

**MUST BE DATE-CORRECT**

Current contract specifications:

**MUST BE MONTHLY VERIFIED**

Unknown specifications:

**MUST NEVER BE INVENTED**

The existing:

```text
~/backtesting/
```

directory is the research root.

Every new strategy gets its own:

```text
~/backtesting/<strategy_name>/
```

directory.

No research strategy may enter:

```text
~/strategy/
```

without explicit user approval.

---

# 27. LIVE STRATEGY EXECUTION & DEPLOYMENT ARCHITECTURE STANDARDS

When preparing, modifying, or operating production trading strategies (e.g. `strategies/liveonopenalgo/` and `strategies/scripts/`):

1. **Zero Blocking Calls in `place_order()`**
   * Never perform synchronous/blocking network calls immediately before or during order submission.
   * Do not call `/positionbook`, `/profile`, or similar pre-flight APIs in the critical order-dispatch path.
   * Order dispatch must remain as fast and reliable as possible.
   * Do not introduce pre-flight checks that can cause a valid trade signal to be lost because of transient API latency.

2. **Mandatory Localhost Loopback on Production EC2**
   * Strategies running on the production EC2 instance must communicate with OpenAlgo through:
     `http://127.0.0.1:5000`
   * Do not use:
     `https://vikashiname.in`
     for internal strategy → OpenAlgo communication.
   * Objective: avoid unnecessary TLS, public DNS, NAT hairpinning and related latency/resource issues.

3. **In-Memory TTL Mode/Environment Cache**
   * Environment and execution-mode checks must use in-memory caching.
   * Default TTL: **60 seconds**.
   * Cache must have a resilient fallback.
   * Do not perform a network request on every trade trigger.

4. **Resilient Notification Transport**
   * Telegram/WhatsApp notification transport must use connection pooling and retries.
   * Use `httpx.HTTPTransport(retries=3)` where applicable.
   * Automatically recreate the HTTP client when an idle connection fails or produces errors such as:
     `UNEXPECTED_EOF_WHILE_READING`
   * Notification failure must not block or prevent trade execution.

5. **In-Place Live Strategy Deployment**
   * For an already-running live strategy, update the existing file in place:
     `/home/ubuntu/fyersawsog/strategies/scripts/<filename>.py`
   * Restart the corresponding systemd service after the approved update.
   * Do NOT re-upload an existing live strategy through the OpenAlgo web UI.
   * Avoid creating duplicate timestamped strategy files.
   * Preserve PID tracking, audit logs and persistent state continuity.

