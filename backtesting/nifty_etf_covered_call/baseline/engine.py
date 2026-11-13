# baseline/engine.py
"""
Mechanical Baseline Backtest Engine for NIFTYBEES Covered Call Strategy.

Strategy:
  Long NIFTYBEES (Cash Equity ETF) + Short NIFTY 50 CE (~2% OTM Monthly Expiry).
  Pure mechanical baseline: Zero optimization, zero indicators, hold to expiry.
  Settle cash intrinsic via NCL clearing price, hold NIFTYBEES, roll next cycle.

Benchmarks:
  1. NIFTYBEES Buy & Hold
  2. NIFTY 50 Spot Reference Buy & Hold
"""

import os
import sys
import glob
import re
import zipfile
from datetime import datetime
import numpy as np
import pandas as pd

# Add openalgo directory to sys.path for Historify
sys.path.insert(0, '/Users/mac/Desktop/openalgo')
from database.historify_db import get_ohlcv

# -----------------------------------------------------------------------------
# 1. PARAMETERS & GOVERNANCE CONSTANTS
# -----------------------------------------------------------------------------
INITIAL_CAPITAL = 1500000.0  # ₹15,00,000 reference capital
RISK_FREE_RATE = 0.065       # 6.5% p.a. (Indian RBI repo / T-bill benchmark)
SLIPPAGE_POINTS_CALL = 0.50  # 0.50 index point slippage on option execution
OTM_TARGET_PCT = 0.02        # 2.0% OTM target strike

# Directory paths
from pathlib import Path
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DATA_DIR = str(ROOT_DIR / 'data')
BASELINE_DIR = str(SCRIPT_DIR)
BHAV_DIR = '/Users/mac/Desktop/openalgo/backtesting/oi/data/raw/bhavcopy'

# -----------------------------------------------------------------------------
# 2. STATUTORY TRANSACTION FEE CALCULATOR
# -----------------------------------------------------------------------------
def calc_equity_costs(turnover: float, side: str = 'BUY') -> dict:
    """Calculate realistic statutory Indian charges for cash equity delivery."""
    brokerage = min(20.0, turnover * 0.0003)  # Flat ₹20 or 0.03%
    stt = turnover * 0.001 if side == 'BUY' else turnover * 0.001  # 0.1% delivery STT
    exch_fee = turnover * 0.0000297  # NSE CM charge 0.00297%
    sebi_fee = turnover * 0.000001   # ₹10 per Crore
    stamp_duty = turnover * 0.00015 if side == 'BUY' else 0.0  # 0.015% buy only
    gst = (brokerage + exch_fee + sebi_fee) * 0.18  # 18% GST
    total = brokerage + stt + exch_fee + sebi_fee + stamp_duty + gst
    return {
        'brokerage': brokerage, 'stt': stt, 'exchange_fee': exch_fee,
        'sebi_fee': sebi_fee, 'stamp_duty': stamp_duty, 'gst': gst, 'total': total
    }

def calc_option_costs(premium_turnover: float, side: str = 'SELL', date_str: str = '2022-01-01') -> dict:
    """Calculate statutory Indian charges for F&O option trading."""
    brokerage = 20.0  # Flat ₹20 per order
    # STT on sell premium: 0.0625% pre-Oct 2024, 0.10% post-Oct 2024
    stt_rate = 0.0010 if date_str >= '2024-10-01' else 0.000625
    stt = premium_turnover * stt_rate if side == 'SELL' else 0.0
    exch_fee = premium_turnover * 0.0003503  # NSE F&O 0.03503%
    sebi_fee = premium_turnover * 0.000001   # ₹10 per Crore
    stamp_duty = premium_turnover * 0.00003 if side == 'BUY' else 0.0
    gst = (brokerage + exch_fee + sebi_fee) * 0.18
    total = brokerage + stt + exch_fee + sebi_fee + stamp_duty + gst
    return {
        'brokerage': brokerage, 'stt': stt, 'exchange_fee': exch_fee,
        'sebi_fee': sebi_fee, 'stamp_duty': stamp_duty, 'gst': gst, 'total': total
    }

# -----------------------------------------------------------------------------
# 3. DATA LOADING & PREPARATION
# -----------------------------------------------------------------------------
def load_market_data():
    """Load NIFTYBEES and NIFTY spot series from Historify."""
    print("Loading underlying data from Historify DuckDB...")
    bees = get_ohlcv('NIFTYBEES', 'NSE', 'D')
    bees['date'] = pd.to_datetime(bees['timestamp'], unit='s').dt.strftime('%Y-%m-%d')
    bees = bees.set_index('date').sort_index()

    nifty = get_ohlcv('NIFTY', 'NSE', 'D')
    nifty['date'] = pd.to_datetime(nifty['timestamp'], unit='s').dt.strftime('%Y-%m-%d')
    nifty = nifty.set_index('date').sort_index()

    # Map bhavcopy files
    files = glob.glob(f'{BHAV_DIR}/*.zip')
    file_map = {}
    for f in files:
        bn = os.path.basename(f)
        m = re.search(r'fo(\d{2}[A-Z]{3}\d{4})bhav', bn)
        if m:
            d = datetime.strptime(m.group(1), '%d%b%Y').strftime('%Y-%m-%d')
            file_map[d] = f
        else:
            m2 = re.search(r'BhavCopy_NSE_FO_0_0_0_(\d{8})_F_0000', bn)
            if m2:
                d = datetime.strptime(m2.group(1), '%Y%m%d').strftime('%Y-%m-%d')
                file_map[d] = f

    return bees, nifty, file_map

def load_bhavcopy_df(file_path):
    """Parse single Bhavcopy zip archive."""
    with zipfile.ZipFile(file_path) as z:
        name = z.namelist()[0]
        df = pd.read_csv(z.open(name))
        if 'INSTRUMENT' in df.columns:
            df = df.rename(columns={
                'INSTRUMENT': 'inst', 'SYMBOL': 'sym', 'EXPIRY_DT': 'expiry',
                'STRIKE_PR': 'strike', 'OPTION_TYP': 'opt_type',
                'OPEN': 'open', 'HIGH': 'high', 'LOW': 'low', 'CLOSE': 'close',
                'SETTLE_PR': 'settle', 'CONTRACTS': 'contracts', 'VAL_INLAKH': 'val_lakh',
                'OPEN_INT': 'oi', 'CHG_IN_OI': 'chg_oi'
            })
        else:
            df = df.rename(columns={
                'FinInstrmTp': 'inst', 'TckrSymb': 'sym', 'XpryDt': 'expiry',
                'StrkPric': 'strike', 'OptnTp': 'opt_type',
                'OpnPric': 'open', 'HghPric': 'high', 'LwPric': 'low', 'ClsPric': 'close',
                'SttlmPric': 'settle', 'TtlTradgVol': 'contracts', 'TtlTrfVal': 'val_lakh',
                'OpnIntrst': 'oi', 'ChngInOpnIntrst': 'chg_oi', 'NewBrdLotQty': 'lot_size'
            })
        for c in ['opt_type', 'sym', 'inst', 'expiry']:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip()
        return df

# -----------------------------------------------------------------------------
# 4. SIMULATION EXECUTION ENGINE
# -----------------------------------------------------------------------------
def run_baseline_backtest():
    """Run mechanical Covered Call simulation across all 31 cycles."""
    bees_df, nifty_df, file_map = load_market_data()
    all_trading_dates = sorted(file_map.keys())

    # Verified 31 monthly expiry calendar metadata
    cycles_meta = [
        ('2022-01-27', ['27-Jan-2022', '27-JAN-2022', '2022-01-27']),
        ('2022-02-24', ['24-Feb-2022', '24-FEB-2022', '2022-02-24']),
        ('2022-03-31', ['31-Mar-2022', '31-MAR-2022', '2022-03-31']),
        ('2022-04-28', ['28-Apr-2022', '28-APR-2022', '2022-04-28']),
        ('2022-05-26', ['26-May-2022', '26-MAY-2022', '2022-05-26']),
        ('2022-06-30', ['30-Jun-2022', '30-JUN-2022', '2022-06-30']),
        ('2022-07-28', ['28-Jul-2022', '28-JUL-2022', '2022-07-28']),
        ('2022-08-25', ['25-Aug-2022', '25-AUG-2022', '2022-08-25']),
        ('2022-09-29', ['29-Sep-2022', '29-SEP-2022', '2022-09-29']),
        ('2022-10-27', ['27-Oct-2022', '27-OCT-2022', '2022-10-27']),
        ('2022-11-24', ['24-Nov-2022', '24-NOV-2022', '2022-11-24']),
        ('2022-12-29', ['29-Dec-2022', '29-DEC-2022', '2022-12-29']),
        ('2023-01-25', ['25-Jan-2023', '25-JAN-2023', '2023-01-25']),
        ('2023-02-23', ['23-Feb-2023', '23-FEB-2023', '2023-02-23']),
        ('2023-03-29', ['29-Mar-2023', '29-MAR-2023', '2023-03-29']),
        ('2023-04-27', ['27-Apr-2023', '27-APR-2023', '2023-04-27']),
        ('2023-05-25', ['25-May-2023', '25-MAY-2023', '2023-05-25']),
        ('2023-06-28', ['29-Jun-2023', '29-JUN-2023', '28-Jun-2023', '28-JUN-2023', '2023-06-28', '2023-06-29']),
        ('2023-07-27', ['27-Jul-2023', '27-JUL-2023', '2023-07-27']),
        ('2023-08-31', ['31-Aug-2023', '31-AUG-2023', '2023-08-31']),
        ('2023-09-28', ['28-Sep-2023', '28-SEP-2023', '2023-09-28']),
        ('2023-10-26', ['26-Oct-2023', '26-OCT-2023', '2023-10-26']),
        ('2023-11-30', ['30-Nov-2023', '30-NOV-2023', '2023-11-30']),
        ('2023-12-28', ['28-Dec-2023', '28-DEC-2023', '2023-12-28']),
        ('2024-01-25', ['25-Jan-2024', '25-JAN-2024', '2024-01-25']),
        ('2024-02-29', ['29-Feb-2024', '29-FEB-2024', '2024-02-29']),
        ('2024-03-28', ['28-Mar-2024', '28-MAR-2024', '2024-03-28']),
        ('2024-04-25', ['25-Apr-2024', '25-APR-2024', '2024-04-25']),
        ('2024-05-30', ['30-May-2024', '30-MAY-2024', '2024-05-30']),
        ('2024-06-27', ['27-Jun-2024', '27-JUN-2024', '2024-06-27']),
        ('2024-07-25', ['25-Jul-2024', '25-JUL-2024', '2024-07-25'])
    ]

    print(f"Executing baseline backtest across {len(cycles_meta)} monthly cycles...")

    # State variables for Strategy Portfolio
    current_cash = INITIAL_CAPITAL
    etf_units_held = 0
    cycle_ledger = []
    
    # State for Benchmarks
    # Benchmark 1: NIFTYBEES Buy & Hold (all initial capital into ETF at Day 1)
    p0_bees = float(bees_df.loc[all_trading_dates[0], 'close'])
    b1_buy_costs = calc_equity_costs(INITIAL_CAPITAL, 'BUY')
    b1_net_cash = INITIAL_CAPITAL - b1_buy_costs['total']
    b1_units = int(b1_net_cash / p0_bees)
    b1_cash_rem = b1_net_cash - (b1_units * p0_bees)

    # Benchmark 2: NIFTY 50 Spot Buy & Hold Reference
    s0_nifty = float(nifty_df.loc[all_trading_dates[0], 'close'])

    prev_exp_date = None

    for cycle_idx, (exp_date, exp_variants) in enumerate(cycles_meta):
        # Entry Date determination
        if cycle_idx == 0:
            entry_date = all_trading_dates[0]
        else:
            prev_idx = all_trading_dates.index(prev_exp_date)
            entry_date = all_trading_dates[prev_idx + 1]

        prev_exp_date = exp_date

        # Lot size rule
        lot_size = 50 if entry_date < '2024-04-26' else 25

        # Market prices
        s_entry = float(nifty_df.loc[entry_date, 'close'])
        p_entry = float(bees_df.loc[entry_date, 'close'])
        s_exit = float(nifty_df.loc[exp_date, 'close'])
        p_exit = float(bees_df.loc[exp_date, 'close'])

        tracking_ratio = s_entry / p_entry
        opt_notional = s_entry * lot_size
        req_bees_units = int(round(opt_notional / p_entry))

        # Initial ETF acquisition on Cycle 1 (or unit adjustment)
        etf_txn_cost = 0.0
        if cycle_idx == 0:
            etf_investment = req_bees_units * p_entry
            costs = calc_equity_costs(etf_investment, 'BUY')
            etf_txn_cost = costs['total']
            etf_units_held = req_bees_units
            current_cash -= (etf_investment + etf_txn_cost)
        else:
            # Sizing adjustment if lot size changed (e.g. from 50 to 25)
            if req_bees_units != etf_units_held:
                diff_units = req_bees_units - etf_units_held
                diff_turnover = abs(diff_units) * p_entry
                if diff_units > 0:
                    costs = calc_equity_costs(diff_turnover, 'BUY')
                    current_cash -= (diff_turnover + costs['total'])
                else:
                    costs = calc_equity_costs(diff_turnover, 'SELL')
                    current_cash += (diff_turnover - costs['total'])
                etf_txn_cost = costs['total']
                etf_units_held = req_bees_units

        # Target Strike Selection (~2.0% OTM)
        target_strike = round((s_entry * (1.0 + OTM_TARGET_PCT)) / 50.0) * 50

        # Load Bhavcopy for entry
        df_entry = load_bhavcopy_df(file_map[entry_date])
        nifty_ce = df_entry[(df_entry['sym'] == 'NIFTY') & (df_entry['opt_type'] == 'CE')]
        opt_matches = nifty_ce[nifty_ce['expiry'].str.upper().isin([x.upper() for x in exp_variants])].copy()
        
        opt_matches['diff'] = (opt_matches['strike'] - target_strike).abs()
        sel_opt = opt_matches.sort_values('diff').iloc[0]
        actual_strike = float(sel_opt['strike'])
        opt_raw_price = float(sel_opt['close']) if float(sel_opt['close']) > 0 else float(sel_opt['settle'])
        
        # Apply adverse slippage on writing the call (sell at bid/lower price)
        opt_fill_price = max(0.05, opt_raw_price - SLIPPAGE_POINTS_CALL)
        gross_premium_collected = opt_fill_price * lot_size
        
        # Option entry transaction costs
        opt_entry_costs = calc_option_costs(gross_premium_collected, 'SELL', entry_date)
        net_premium_credited = gross_premium_collected - opt_entry_costs['total']
        current_cash += net_premium_credited

        # Expiry Day Settlement
        df_exit = load_bhavcopy_df(file_map[exp_date])
        exit_ce = df_exit[(df_exit['sym'] == 'NIFTY') & (df_exit['opt_type'] == 'CE')]
        exit_matches = exit_ce[(exit_ce['expiry'].str.upper().isin([x.upper() for x in exp_variants])) & 
                               (exit_ce['strike'] == actual_strike)]
        
        intrinsic = max(0.0, s_exit - actual_strike)
        is_itm = s_exit > actual_strike
        cash_settle_debit = intrinsic * lot_size

        # Deduct cash debit directly from cash balance
        current_cash -= cash_settle_debit

        # Cycle P&L decomposition
        etf_val_entry = etf_units_held * p_entry
        etf_val_exit = etf_units_held * p_exit
        etf_gross_pnl = etf_val_exit - etf_val_entry
        etf_net_pnl = etf_gross_pnl - etf_txn_cost

        opt_gross_pnl = (opt_fill_price - intrinsic) * lot_size
        opt_net_pnl = opt_gross_pnl - opt_entry_costs['total']

        total_cycle_pnl = etf_net_pnl + opt_net_pnl
        total_portfolio_equity = current_cash + etf_val_exit

        # Benchmark 1 Equity on expiry day
        b1_equity = (b1_units * p_exit) + b1_cash_rem

        # Benchmark 2 Reference Equity on expiry day
        b2_equity = INITIAL_CAPITAL * (s_exit / s0_nifty)

        cycle_ledger.append({
            'cycle': cycle_idx + 1,
            'entry_date': entry_date,
            'expiry_date': exp_date,
            'lot_size': lot_size,
            's_entry': s_entry,
            'p_entry': p_entry,
            'tracking_ratio': tracking_ratio,
            'etf_units': etf_units_held,
            'strike': actual_strike,
            'otm_pct': (actual_strike - s_entry) / s_entry * 100.0,
            'opt_raw_price': opt_raw_price,
            'opt_fill_price': opt_fill_price,
            'gross_premium': gross_premium_collected,
            'opt_costs': opt_entry_costs['total'],
            'etf_costs': etf_txn_cost,
            's_exit': s_exit,
            'p_exit': p_exit,
            'is_itm': is_itm,
            'intrinsic': intrinsic,
            'cash_debit': cash_settle_debit,
            'etf_net_pnl': etf_net_pnl,
            'opt_net_pnl': opt_net_pnl,
            'cycle_net_pnl': total_cycle_pnl,
            'closing_cash': current_cash,
            'closing_etf_value': etf_val_exit,
            'portfolio_equity': total_portfolio_equity,
            'b1_equity_bees': b1_equity,
            'b2_equity_nifty': b2_equity,
            'etf_ret_pct': (p_exit - p_entry) / p_entry * 100.0,
            'spot_ret_pct': (s_exit - s_entry) / s_entry * 100.0,
            'cc_ret_pct': total_cycle_pnl / (total_portfolio_equity - total_cycle_pnl) * 100.0
        })

    ledger_df = pd.DataFrame(cycle_ledger)
    
    # Save artifacts
    ledger_df.to_parquet(f'{BASELINE_DIR}/cycle_ledger.parquet')
    ledger_df.to_csv(f'{BASELINE_DIR}/cycle_ledger.csv', index=False)
    print(f"Cycle ledger saved to {BASELINE_DIR}/cycle_ledger.parquet & .csv")

    return ledger_df

# -----------------------------------------------------------------------------
# 5. PERFORMANCE & RISK METRICS ENGINE
# -----------------------------------------------------------------------------
def compute_metrics(ledger_df):
    """Compute institutional quantitative risk/return metrics."""
    final_cc_equity = ledger_df['portfolio_equity'].iloc[-1]
    final_b1_equity = ledger_df['b1_equity_bees'].iloc[-1]
    final_b2_equity = ledger_df['b2_equity_nifty'].iloc[-1]

    total_cc_return = (final_cc_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    total_b1_return = (final_b1_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    total_b2_return = (final_b2_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0

    # Horizon in years
    start_dt = datetime.strptime(ledger_df['entry_date'].iloc[0], '%Y-%m-%d')
    end_dt = datetime.strptime(ledger_df['expiry_date'].iloc[-1], '%Y-%m-%d')
    years = (end_dt - start_dt).days / 365.25

    cagr_cc = ((final_cc_equity / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    cagr_b1 = ((final_b1_equity / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0
    cagr_b2 = ((final_b2_equity / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0

    # Max Drawdowns
    def calc_mdd(series):
        peak = series.cummax()
        dd = (series - peak) / peak
        return dd.min() * 100.0

    mdd_cc = calc_mdd(ledger_df['portfolio_equity'])
    mdd_b1 = calc_mdd(ledger_df['b1_equity_bees'])
    mdd_b2 = calc_mdd(ledger_df['b2_equity_nifty'])

    # Annualized Volatility & Sharpe Ratio
    rf_monthly = (1.0 + RISK_FREE_RATE) ** (1.0 / 12.0) - 1.0
    monthly_ret_cc = ledger_df['cc_ret_pct'] / 100.0
    monthly_ret_b1 = (ledger_df['b1_equity_bees'].pct_change()).fillna(
        (ledger_df['b1_equity_bees'].iloc[0] - INITIAL_CAPITAL) / INITIAL_CAPITAL
    )

    vol_cc = monthly_ret_cc.std() * np.sqrt(12) * 100.0
    vol_b1 = monthly_ret_b1.std() * np.sqrt(12) * 100.0

    sharpe_cc = (cagr_cc / 100.0 - RISK_FREE_RATE) / (vol_cc / 100.0) if vol_cc > 0 else 0.0
    sharpe_b1 = (cagr_b1 / 100.0 - RISK_FREE_RATE) / (vol_b1 / 100.0) if vol_b1 > 0 else 0.0

    # Downside Volatility & Sortino Ratio
    downside_cc = monthly_ret_cc[monthly_ret_cc < 0.0].std() * np.sqrt(12) * 100.0
    downside_b1 = monthly_ret_b1[monthly_ret_b1 < 0.0].std() * np.sqrt(12) * 100.0

    sortino_cc = (cagr_cc / 100.0 - RISK_FREE_RATE) / (downside_cc / 100.0) if downside_cc > 0 else 0.0
    sortino_b1 = (cagr_b1 / 100.0 - RISK_FREE_RATE) / (downside_b1 / 100.0) if downside_b1 > 0 else 0.0

    # Win rate & Profit factor
    profitable_cycles = len(ledger_df[ledger_df['cycle_net_pnl'] > 0])
    win_rate = profitable_cycles / len(ledger_df) * 100.0

    gross_gains = ledger_df[ledger_df['cycle_net_pnl'] > 0]['cycle_net_pnl'].sum()
    gross_losses = abs(ledger_df[ledger_df['cycle_net_pnl'] < 0]['cycle_net_pnl'].sum())
    profit_factor = gross_gains / gross_losses if gross_losses > 0 else np.nan

    # Cash flow metrics
    total_opt_costs = ledger_df['opt_costs'].sum()
    total_etf_costs = ledger_df['etf_costs'].sum()
    total_frictions = total_opt_costs + total_etf_costs
    total_prems_collected = ledger_df['gross_premium'].sum()
    total_cash_debits = ledger_df['cash_debit'].sum()

    metrics = {
        'initial_capital': INITIAL_CAPITAL,
        'final_equity_cc': final_cc_equity,
        'final_equity_b1': final_b1_equity,
        'final_equity_b2': final_b2_equity,
        'total_return_cc': total_cc_return,
        'total_return_b1': total_b1_return,
        'total_return_b2': total_b2_return,
        'cagr_cc': cagr_cc,
        'cagr_b1': cagr_b1,
        'cagr_b2': cagr_b2,
        'mdd_cc': mdd_cc,
        'mdd_b1': mdd_b1,
        'mdd_b2': mdd_b2,
        'vol_cc': vol_cc,
        'vol_b1': vol_b1,
        'sharpe_cc': sharpe_cc,
        'sharpe_b1': sharpe_b1,
        'sortino_cc': sortino_cc,
        'sortino_b1': sortino_b1,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_premium_collected': total_prems_collected,
        'total_cash_debits': total_cash_debits,
        'total_frictions': total_frictions,
        'opt_net_pnl': ledger_df['opt_net_pnl'].sum(),
        'etf_net_pnl': ledger_df['etf_net_pnl'].sum(),
        'years': years
    }
    return metrics

if __name__ == '__main__':
    df = run_baseline_backtest()
    m = compute_metrics(df)
    print("\n=======================================================")
    print("      MECHANICAL BASELINE BACKTEST RESULTS SUMMARY     ")
    print("=======================================================")
    print(f"Horizon: {m['years']:.2f} Years (31 Monthly Cycles)")
    print(f"Initial Reference Capital: ₹{m['initial_capital']:,.2f}")
    print(f"Covered Call Final Equity: ₹{m['final_equity_cc']:,.2f} ({m['total_return_cc']:+.2f}%, CAGR: {m['cagr_cc']:.2f}%)")
    print(f"NIFTYBEES B&H Equity:      ₹{m['final_equity_b1']:,.2f} ({m['total_return_b1']:+.2f}%, CAGR: {m['cagr_b1']:.2f}%)")
    print(f"NIFTY 50 Spot Reference:   ₹{m['final_equity_b2']:,.2f} ({m['total_return_b2']:+.2f}%, CAGR: {m['cagr_b2']:.2f}%)")
    print("-------------------------------------------------------")
    print(f"Max Drawdown:  Covered Call: {m['mdd_cc']:.2f}% | NIFTYBEES B&H: {m['mdd_b1']:.2f}%")
    print(f"Annual Vol:    Covered Call: {m['vol_cc']:.2f}% | NIFTYBEES B&H: {m['vol_b1']:.2f}%")
    print(f"Sharpe Ratio:  Covered Call: {m['sharpe_cc']:.2f}  | NIFTYBEES B&H: {m['sharpe_b1']:.2f}")
    print(f"Sortino Ratio: Covered Call: {m['sortino_cc']:.2f}  | NIFTYBEES B&H: {m['sortino_b1']:.2f}")
    print(f"Win Rate:      {m['win_rate']:.1f}% ({int(m['win_rate']/100*31)} / 31 cycles)")
    print(f"Profit Factor: {m['profit_factor']:.2f}")
    print("-------------------------------------------------------")
    print(f"Gross Premium Collected: ₹{m['total_premium_collected']:,.2f}")
    print(f"Total Cash Debited (ITM): ₹{m['total_cash_debits']:,.2f}")
    print(f"Total Statutory Friction: ₹{m['total_frictions']:,.2f}")
    print(f"Option Leg Net P&L:       ₹{m['opt_net_pnl']:,.2f}")
    print(f"NIFTYBEES Leg Net P&L:    ₹{m['etf_net_pnl']:,.2f}")
    print("=======================================================")
