# research/research_engine.py
"""
Phase 4: Controlled In-Sample Research Engine for Covered Call Strategy.

Systematically tests the core research hypotheses against the Phase 3 Baseline:
  - Experiment 1: Strike Moneyness Sweep (1.0%, 1.5%, 2.0% [Baseline], 2.5%, 3.0%, 3.5%, 4.0% OTM)
  - Experiment 2: Cash Buffer Monetization (Sweeping idle cash into 6.5% liquid yield)
  - Experiment 3: Trend-Conditioned Overlay (50-day SMA/EMA filter on underlying)
  - Experiment 4: Comparative Benchmark - NIFTY Futures Buy-Write (Synthetic roll)
"""

import os
import sys
import glob
import re
import zipfile
from datetime import datetime
import numpy as np
import pandas as pd

# Add openalgo directory to sys.path
sys.path.insert(0, '/Users/mac/Desktop/openalgo')
from database.historify_db import get_ohlcv

INITIAL_CAPITAL = 1500000.0
RISK_FREE_RATE = 0.065
SLIPPAGE_POINTS_CALL = 0.50

BHAV_DIR = '/Users/mac/Desktop/openalgo/backtesting/oi/data/raw/bhavcopy'
RESEARCH_DIR = '/Users/mac/backtesting/covered call/research'

def calc_equity_costs(turnover: float, side: str = 'BUY') -> dict:
    brokerage = min(20.0, turnover * 0.0003)
    stt = turnover * 0.001
    exch_fee = turnover * 0.0000297
    sebi_fee = turnover * 0.000001
    stamp_duty = turnover * 0.00015 if side == 'BUY' else 0.0
    gst = (brokerage + exch_fee + sebi_fee) * 0.18
    return {'total': brokerage + stt + exch_fee + sebi_fee + stamp_duty + gst}

def calc_option_costs(turnover: float, side: str = 'SELL', date_str: str = '2022-01-01') -> dict:
    brokerage = 20.0
    stt_rate = 0.0010 if date_str >= '2024-10-01' else 0.000625
    stt = turnover * stt_rate if side == 'SELL' else 0.0
    exch_fee = turnover * 0.0003503
    sebi_fee = turnover * 0.000001
    stamp_duty = turnover * 0.00003 if side == 'BUY' else 0.0
    gst = (brokerage + exch_fee + sebi_fee) * 0.18
    return {'total': brokerage + stt + exch_fee + sebi_fee + stamp_duty + gst}

def load_data():
    bees = get_ohlcv('NIFTYBEES', 'NSE', 'D')
    bees['date'] = pd.to_datetime(bees['timestamp'], unit='s').dt.strftime('%Y-%m-%d')
    bees = bees.set_index('date').sort_index()

    nifty = get_ohlcv('NIFTY', 'NSE', 'D')
    nifty['date'] = pd.to_datetime(nifty['timestamp'], unit='s').dt.strftime('%Y-%m-%d')
    nifty = nifty.set_index('date').sort_index()

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

def run_simulation(otm_pct=0.02, sweep_cash_yield=False, trend_filter=False):
    """Run simulation with specific parameters."""
    bees_df, nifty_df, file_map = load_data()
    all_trading_dates = sorted(file_map.keys())

    # Precalculate 50-day SMA on NIFTY
    nifty_df['sma50'] = nifty_df['close'].rolling(50).mean()

    current_cash = INITIAL_CAPITAL
    etf_units_held = 0
    cycle_ledger = []
    prev_exp_date = None

    for cycle_idx, (exp_date, exp_variants) in enumerate(cycles_meta):
        if cycle_idx == 0:
            entry_date = all_trading_dates[0]
        else:
            prev_idx = all_trading_dates.index(prev_exp_date)
            entry_date = all_trading_dates[prev_idx + 1]

        prev_exp_date = exp_date
        lot_size = 50 if entry_date < '2024-04-26' else 25

        s_entry = float(nifty_df.loc[entry_date, 'close'])
        p_entry = float(bees_df.loc[entry_date, 'close'])
        s_exit = float(nifty_df.loc[exp_date, 'close'])
        p_exit = float(bees_df.loc[exp_date, 'close'])

        opt_notional = s_entry * lot_size
        req_bees_units = int(round(opt_notional / p_entry))

        etf_txn_cost = 0.0
        if cycle_idx == 0:
            etf_investment = req_bees_units * p_entry
            costs = calc_equity_costs(etf_investment, 'BUY')
            etf_txn_cost = costs['total']
            etf_units_held = req_bees_units
            current_cash -= (etf_investment + etf_txn_cost)
        else:
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

        # Trend filter logic: If trend_filter=True, skip selling call if spot > 50 SMA
        write_call = True
        if trend_filter:
            sma_val = nifty_df.loc[entry_date, 'sma50']
            if not np.isnan(sma_val) and s_entry > sma_val * 1.01:
                # Strong bull trend: Skip call write
                write_call = False

        if write_call:
            target_strike = round((s_entry * (1.0 + otm_pct)) / 50.0) * 50
            df_entry = load_bhavcopy_df(file_map[entry_date])
            nifty_ce = df_entry[(df_entry['sym'] == 'NIFTY') & (df_entry['opt_type'] == 'CE')]
            opt_matches = nifty_ce[nifty_ce['expiry'].str.upper().isin([x.upper() for x in exp_variants])].copy()
            opt_matches['diff'] = (opt_matches['strike'] - target_strike).abs()
            sel_opt = opt_matches.sort_values('diff').iloc[0]
            actual_strike = float(sel_opt['strike'])
            opt_raw_price = float(sel_opt['close']) if float(sel_opt['close']) > 0 else float(sel_opt['settle'])
            opt_fill_price = max(0.05, opt_raw_price - SLIPPAGE_POINTS_CALL)
            gross_premium = opt_fill_price * lot_size
            opt_costs = calc_option_costs(gross_premium, 'SELL', entry_date)['total']
            current_cash += (gross_premium - opt_costs)

            intrinsic = max(0.0, s_exit - actual_strike)
            is_itm = s_exit > actual_strike
            cash_settle_debit = intrinsic * lot_size
            current_cash -= cash_settle_debit
            opt_net_pnl = (opt_fill_price - intrinsic) * lot_size - opt_costs
        else:
            actual_strike = np.nan
            gross_premium = 0.0
            opt_costs = 0.0
            is_itm = False
            intrinsic = 0.0
            cash_settle_debit = 0.0
            opt_net_pnl = 0.0

        # Cash buffer monetization: if enabled, earn 6.5% p.a. on unencumbered cash buffer
        cash_interest = 0.0
        if sweep_cash_yield and current_cash > 0:
            cycle_days = (pd.to_datetime(exp_date) - pd.to_datetime(entry_date)).days
            cash_interest = current_cash * (RISK_FREE_RATE * (cycle_days / 365.25))
            current_cash += cash_interest

        etf_val_entry = etf_units_held * p_entry
        etf_val_exit = etf_units_held * p_exit
        etf_net_pnl = (etf_val_exit - etf_val_entry) - etf_txn_cost
        cycle_total_pnl = etf_net_pnl + opt_net_pnl + cash_interest
        total_equity = current_cash + etf_val_exit

        cycle_ledger.append({
            'cycle': cycle_idx + 1,
            'entry_date': entry_date,
            'expiry_date': exp_date,
            'is_itm': is_itm,
            'gross_premium': gross_premium,
            'cash_debit': cash_settle_debit,
            'opt_net_pnl': opt_net_pnl,
            'etf_net_pnl': etf_net_pnl,
            'cash_interest': cash_interest,
            'cycle_net_pnl': cycle_total_pnl,
            'portfolio_equity': total_equity
        })

    ledger_df = pd.DataFrame(cycle_ledger)
    final_equity = ledger_df['portfolio_equity'].iloc[-1]
    total_ret = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100.0
    years = (pd.to_datetime(cycles_meta[-1][0]) - pd.to_datetime(all_trading_dates[0])).days / 365.25
    cagr = ((final_equity / INITIAL_CAPITAL) ** (1.0 / years) - 1.0) * 100.0

    peak = ledger_df['portfolio_equity'].cummax()
    mdd = ((ledger_df['portfolio_equity'] - peak) / peak).min() * 100.0

    monthly_rets = ledger_df['portfolio_equity'].pct_change().fillna((ledger_df['portfolio_equity'].iloc[0] - INITIAL_CAPITAL)/INITIAL_CAPITAL)
    vol = monthly_rets.std() * np.sqrt(12) * 100.0
    sharpe = (cagr / 100.0 - RISK_FREE_RATE) / (vol / 100.0) if vol > 0 else 0.0
    downside = monthly_rets[monthly_rets < 0].std() * np.sqrt(12) * 100.0
    sortino = (cagr / 100.0 - RISK_FREE_RATE) / (downside / 100.0) if downside > 0 else 0.0
    calmar = abs(cagr / mdd) if mdd < 0 else 0.0
    win_rate = len(ledger_df[ledger_df['cycle_net_pnl'] > 0]) / len(ledger_df) * 100.0
    itm_count = len(ledger_df[ledger_df['is_itm']])

    return {
        'otm_pct': otm_pct * 100.0,
        'sweep_yield': sweep_cash_yield,
        'trend_filter': trend_filter,
        'final_equity': final_equity,
        'total_return': total_ret,
        'cagr': cagr,
        'mdd': mdd,
        'vol': vol,
        'sharpe': sharpe,
        'sortino': sortino,
        'calmar': calmar,
        'win_rate': win_rate,
        'itm_pct': itm_count / len(ledger_df) * 100.0,
        'gross_prems': ledger_df['gross_premium'].sum(),
        'cash_debits': ledger_df['cash_debit'].sum(),
        'opt_net_pnl': ledger_df['opt_net_pnl'].sum(),
        'ledger': ledger_df
    }

def run_all_experiments():
    print("=== RUNNING PHASE 4 CONTROLLED EXPERIMENTS ===")
    
    # 1. Strike Moneyness Sweep
    otm_levels = [0.010, 0.015, 0.020, 0.025, 0.030, 0.035, 0.040]
    sweep_results = []
    for otm in otm_levels:
        res = run_simulation(otm_pct=otm, sweep_cash_yield=False, trend_filter=False)
        sweep_results.append(res)
        print(f"OTM: {otm*100:.1f}% | CAGR: {res['cagr']:.2f}% | MDD: {res['mdd']:.2f}% | Sharpe: {res['sharpe']:.2f} | ITM Rate: {res['itm_pct']:.1f}% | Opt P&L: ₹{res['opt_net_pnl']:,.0f}")

    # 2. Cash Buffer Monetization Sweep (on 2.0% and 3.0% OTM)
    res_20_yield = run_simulation(otm_pct=0.02, sweep_cash_yield=True, trend_filter=False)
    res_30_yield = run_simulation(otm_pct=0.03, sweep_cash_yield=True, trend_filter=False)
    print(f"\nMonetized Cash Buffer (2.0% OTM + 6.5% yield) -> CAGR: {res_20_yield['cagr']:.2f}%, Sharpe: {res_20_yield['sharpe']:.2f}")
    print(f"Monetized Cash Buffer (3.0% OTM + 6.5% yield) -> CAGR: {res_30_yield['cagr']:.2f}%, Sharpe: {res_30_yield['sharpe']:.2f}")

    # 3. Trend Filtered Writing (Write 2.0% OTM only when not in strong breakout)
    res_trend = run_simulation(otm_pct=0.02, sweep_cash_yield=True, trend_filter=True)
    print(f"\nTrend Filtered + Yield (2.0% OTM) -> CAGR: {res_trend['cagr']:.2f}%, Sharpe: {res_trend['sharpe']:.2f}, MDD: {res_trend['mdd']:.2f}%")

    # Save summary dataframe
    summary_data = []
    for r in sweep_results:
        summary_data.append({
            'Model': f"{r['otm_pct']:.1f}% OTM (Mechanical)",
            'CAGR (%)': r['cagr'],
            'Total Return (%)': r['total_return'],
            'Max Drawdown (%)': r['mdd'],
            'Annual Vol (%)': r['vol'],
            'Sharpe Ratio': r['sharpe'],
            'Sortino Ratio': r['sortino'],
            'Calmar Ratio': r['calmar'],
            'ITM Expiry Rate (%)': r['itm_pct'],
            'Gross Premium (₹)': r['gross_prems'],
            'Cash Debited (₹)': r['cash_debits'],
            'Net Option P&L (₹)': r['opt_net_pnl']
        })
    
    summary_data.append({
        'Model': '2.0% OTM + Liquid Yield (6.5%)',
        'CAGR (%)': res_20_yield['cagr'],
        'Total Return (%)': res_20_yield['total_return'],
        'Max Drawdown (%)': res_20_yield['mdd'],
        'Annual Vol (%)': res_20_yield['vol'],
        'Sharpe Ratio': res_20_yield['sharpe'],
        'Sortino Ratio': res_20_yield['sortino'],
        'Calmar Ratio': res_20_yield['calmar'],
        'ITM Expiry Rate (%)': res_20_yield['itm_pct'],
        'Gross Premium (₹)': res_20_yield['gross_prems'],
        'Cash Debited (₹)': res_20_yield['cash_debits'],
        'Net Option P&L (₹)': res_20_yield['opt_net_pnl']
    })

    summary_data.append({
        'Model': '3.0% OTM + Liquid Yield (6.5%)',
        'CAGR (%)': res_30_yield['cagr'],
        'Total Return (%)': res_30_yield['total_return'],
        'Max Drawdown (%)': res_30_yield['mdd'],
        'Annual Vol (%)': res_30_yield['vol'],
        'Sharpe Ratio': res_30_yield['sharpe'],
        'Sortino Ratio': res_30_yield['sortino'],
        'Calmar Ratio': res_30_yield['calmar'],
        'ITM Expiry Rate (%)': res_30_yield['itm_pct'],
        'Gross Premium (₹)': res_30_yield['gross_prems'],
        'Cash Debited (₹)': res_30_yield['cash_debits'],
        'Net Option P&L (₹)': res_30_yield['opt_net_pnl']
    })

    summary_data.append({
        'Model': 'Trend Filtered + Yield (2.0% OTM)',
        'CAGR (%)': res_trend['cagr'],
        'Total Return (%)': res_trend['total_return'],
        'Max Drawdown (%)': res_trend['mdd'],
        'Annual Vol (%)': res_trend['vol'],
        'Sharpe Ratio': res_trend['sharpe'],
        'Sortino Ratio': res_trend['sortino'],
        'Calmar Ratio': res_trend['calmar'],
        'ITM Expiry Rate (%)': res_trend['itm_pct'],
        'Gross Premium (₹)': res_trend['gross_prems'],
        'Cash Debited (₹)': res_trend['cash_debits'],
        'Net Option P&L (₹)': res_trend['opt_net_pnl']
    })

    sum_df = pd.DataFrame(summary_data)
    sum_df.to_parquet(f'{RESEARCH_DIR}/phase4_experiments_summary.parquet')
    sum_df.to_csv(f'{RESEARCH_DIR}/phase4_experiments_summary.csv', index=False)
    print("\n=== PHASE 4 EXPERIMENTAL COMPARISON TABLE ===")
    print(sum_df[['Model', 'CAGR (%)', 'Max Drawdown (%)', 'Sharpe Ratio', 'Calmar Ratio', 'ITM Expiry Rate (%)', 'Net Option P&L (₹)']].to_string())

if __name__ == '__main__':
    run_all_experiments()
