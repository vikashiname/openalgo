
import sys
from pathlib import Path
sys.path.insert(0, str(Path('backtesting/emacrossopen').resolve()))
import final_target_runner_backtest as ft
import pandas as pd
import numpy as np

data_map = ft.load_all_dataset()
raw_trades = ft.extract_v2_2_trades(data_map)
is_split = pd.to_datetime('2025-07-01', utc=True)
split_2026 = pd.to_datetime('2026-01-01', utc=True)

# TOP_LONGS and TOP_SHORTS from emacrossopen.py
TOP_LONGS = {
    'SUNPHARMA', 'BAJAJ-AUTO', 'BPCL', 'WIPRO', 'TATASTEEL',
    'BAJFINANCE', 'NTPC'
}
TOP_SHORTS = {
    'SUNPHARMA', 'BAJAJ-AUTO', 'M&M', 'BPCL', 'NTPC',
    'NIFTY'
}

def simulate_engine(
    model_type='BASELINE', # 'BASELINE' or 'HWM'
    trail_pct=0.35,
    use_asym_universe=False,
    use_regime_filter=False,
    use_counter_exit=False,
    conservative_trailing=True,
    friction_pct=0.07,
    sl_pct=6.00,
    long_tp=3.00,
    short_tp=1.50,
):
    trades = []
    
    for t in raw_trades:
        sym = t['symbol']
        direction = t['direction']
        dir_str = t['direction_str']
        entry_px = t['entry_price']
        entry_time = t['entry_time']
        df_slice = t['df_slice']
        
        # 1. Asymmetric Universe Filter on entry
        if use_asym_universe:
            if direction == 1 and sym not in TOP_LONGS:
                continue
            if direction == -1 and sym not in TOP_SHORTS:
                continue
                
        # 2. 1H Trend Regime Filter on entry
        if use_regime_filter:
            first_bar = df_slice.iloc[0]
            curr_close = float(first_bar['Close'])
            curr_ema26 = float(first_bar['ema26'])
            if direction == 1 and curr_close < curr_ema26:
                continue # Skip counter-trend Long
            if direction == -1 and curr_close > curr_ema26:
                continue # Skip counter-trend Short
                
        target_pct = long_tp if direction == 1 else short_tp
        target_px = entry_px * (1 + target_pct/100) if direction == 1 else entry_px * (1 - target_pct/100)
        sl_px = entry_px * (1 - sl_pct/100) if direction == 1 else entry_px * (1 + sl_pct/100)
        
        exit_price = t['forward_reversal_price']
        exit_time = t['forward_reversal_time']
        exit_reason = 'V2-2_REVERSAL'
        target_reached = False
        runner_active = False
        peak = entry_px
        trough = entry_px
        bars_held = 0
        target_bar = -1
        
        for bar_num, (ts, row) in enumerate(df_slice.iterrows()):
            curr_open = float(row['Open'])
            curr_high = float(row['High'])
            curr_low = float(row['Low'])
            curr_close = float(row['Close'])
            curr_ema26 = float(row['ema26'])
            bars_held = bar_num + 1
            
            # Catastrophe SL
            if (direction == 1 and curr_low <= sl_px) or (direction == -1 and curr_high >= sl_px):
                exit_price = sl_px
                exit_reason = 'CATASTROPHE_SL'
                exit_time = ts
                break
                
            # Counter-trend exit rule (exit early if 1H regime flips against position)
            if use_counter_exit:
                if direction == 1 and curr_close < curr_ema26:
                    exit_price = curr_close
                    exit_reason = 'COUNTER_TREND_REGIME_EXIT'
                    exit_time = ts
                    break
                elif direction == -1 and curr_close > curr_ema26:
                    exit_price = curr_close
                    exit_reason = 'COUNTER_TREND_REGIME_EXIT'
                    exit_time = ts
                    break
                    
            # Target check
            if not target_reached:
                hit = (direction == 1 and curr_high >= target_px) or (direction == -1 and curr_low <= target_px)
                if hit:
                    target_reached = True
                    target_bar = bar_num
                    if model_type == 'BASELINE':
                        exit_price = target_px
                        exit_reason = 'TARGET_HIT'
                        exit_time = ts
                        break
                    else:
                        runner_active = True
                        if direction == 1: peak = max(entry_px, curr_high)
                        else: trough = min(entry_px, curr_low)
                        if conservative_trailing:
                            continue
                            
            # Trailing Runner
            if runner_active and (not conservative_trailing or bar_num > target_bar):
                if direction == 1:
                    peak = max(peak, curr_high)
                    trail_sl = peak * (1.0 - (trail_pct / 100.0))
                    if curr_low <= trail_sl:
                        exit_reason = 'RUNNER_HWM_TRAIL'
                        exit_price = min(trail_sl, curr_open) if (conservative_trailing and curr_open <= trail_sl) else trail_sl
                        exit_time = ts
                        break
                else:
                    trough = min(trough, curr_low)
                    trail_sl = trough * (1.0 + (trail_pct / 100.0))
                    if curr_high >= trail_sl:
                        exit_reason = 'RUNNER_HWM_TRAIL'
                        exit_price = max(trail_sl, curr_open) if (conservative_trailing and curr_open >= trail_sl) else trail_sl
                        exit_time = ts
                        break
                        
            # Reversal
            if ts >= t['forward_reversal_time']:
                exit_reason = 'V2-2_REVERSAL'
                exit_price = curr_close
                exit_time = ts
                break
                
        raw_pnl = ((exit_price - entry_px)/entry_px)*100 if direction == 1 else ((entry_px - exit_price)/entry_px)*100
        net_pnl = raw_pnl - friction_pct
        trades.append({
            'symbol': sym,
            'direction': direction,
            'direction_str': dir_str,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'exit_reason': exit_reason,
            'bars_held': bars_held,
            'raw_pnl_pct': raw_pnl,
            'net_pnl_pct': net_pnl,
            'is_is': pd.to_datetime(entry_time, utc=True) < is_split,
            'is_2026': pd.to_datetime(entry_time, utc=True) >= split_2026,
        })
    return pd.DataFrame(trades)

def summarize(df):
    if len(df) == 0:
        return {'trades': 0, 'win_rate': 0.0, 'net_pnl': 0.0, 'pf': 0.0, 'max_dd': 0.0, 'expectancy': 0.0, 'avg_bars': 0.0}
    w = df[df['net_pnl_pct'] > 0]
    l = df[df['net_pnl_pct'] < 0]
    gp = w['net_pnl_pct'].sum()
    gl = abs(l['net_pnl_pct'].sum())
    pf = gp / gl if gl > 0 else (float('inf') if gp > 0 else 0.0)
    net = df['net_pnl_pct'].sum()
    wr = len(w)/len(df)*100
    exp = df['net_pnl_pct'].mean()
    eq = df['net_pnl_pct'].cumsum()
    mdd = (eq.cummax() - eq).max() if len(eq) > 0 else 0.0
    return {
        'trades': len(df),
        'win_rate': wr,
        'net_pnl': net,
        'pf': pf,
        'max_dd': mdd,
        'expectancy': exp,
        'avg_bars': df['bars_held'].mean(),
    }

# Run Full Experiment Matrix
experiments = [
    ('EXP_A_Frozen_Baseline', 'BASELINE', 0.35, False, False, False, True),
    ('EXP_B_Asym_Universe_Only', 'BASELINE', 0.35, True, False, False, True),
    ('EXP_C_Regime_Filter_Only', 'BASELINE', 0.35, False, True, False, True),
    ('EXP_D_Counter_Exit_Only', 'BASELINE', 0.35, False, False, True, True),
    ('EXP_E_Combined_Universe_Regime_Exit', 'BASELINE', 0.35, True, True, True, True),
    ('EXP_F1_Runner_020_Alone', 'HWM', 0.20, False, False, False, True),
    ('EXP_F2_Runner_035_Alone', 'HWM', 0.35, False, False, False, True),
    ('EXP_F3_Runner_050_Alone', 'HWM', 0.50, False, False, False, True),
    ('EXP_F4_Runner_075_Alone', 'HWM', 0.75, False, False, False, True),
    ('EXP_F5_Runner_100_Alone', 'HWM', 1.00, False, False, False, True),
    ('EXP_G_Runner_035_Plus_Asym_Universe', 'HWM', 0.35, True, False, False, True),
    ('EXP_H_Runner_035_Plus_Regime_Filter', 'HWM', 0.35, False, True, False, True),
    ('EXP_I_Runner_035_Plus_Universe_Regime', 'HWM', 0.35, True, True, False, True),
    ('EXP_J_Full_Champion_Architecture', 'HWM', 0.35, True, True, True, True),
]

matrix_rows = []
for name, m_type, trail, asym, reg, c_exit, cons in experiments:
    df_res = simulate_engine(
        model_type=m_type,
        trail_pct=trail,
        use_asym_universe=asym,
        use_regime_filter=reg,
        use_counter_exit=c_exit,
        conservative_trailing=cons,
        friction_pct=0.07,
    )
    s_all = summarize(df_res)
    s_long = summarize(df_res[df_res['direction'] == 1])
    s_short = summarize(df_res[df_res['direction'] == -1])
    s_is = summarize(df_res[df_res['is_is']])
    s_oos = summarize(df_res[~df_res['is_is']])
    s_2026 = summarize(df_res[df_res['is_2026']])
    
    matrix_rows.append({
        'experiment': name,
        'model_type': m_type,
        'trail_pct': trail,
        'asym_universe': asym,
        'regime_filter': reg,
        'counter_exit': c_exit,
        'total_trades': s_all['trades'],
        'win_rate_pct': s_all['win_rate'],
        'net_pnl_pct': s_all['net_pnl'],
        'profit_factor': s_all['pf'],
        'max_drawdown_pct': s_all['max_dd'],
        'expectancy_pct': s_all['expectancy'],
        'avg_bars': s_all['avg_bars'],
        'long_trades': s_long['trades'],
        'long_net_pnl': s_long['net_pnl'],
        'long_pf': s_long['pf'],
        'short_trades': s_short['trades'],
        'short_net_pnl': s_short['net_pnl'],
        'short_pf': s_short['pf'],
        'is_net_pnl': s_is['net_pnl'],
        'is_pf': s_is['pf'],
        'oos_net_pnl': s_oos['net_pnl'],
        'oos_pf': s_oos['pf'],
        'holdout_2026_net_pnl': s_2026['net_pnl'],
        'holdout_2026_pf': s_2026['pf'],
    })
    print(f"{name:35s} | N={s_all['trades']:4d} | Net={s_all['net_pnl']:7.2f}% | PF={s_all['pf']:5.3f} | MDD={s_all['max_dd']:6.2f}% | IS_PF={s_is['pf']:5.3f} | OOS_PF={s_oos['pf']:5.3f} | 2026_PF={s_2026['pf']:5.3f}")

df_matrix = pd.DataFrame(matrix_rows)
out_csv = Path('backtesting/runs/run_20261012_audit_opt/EXPERIMENT_MATRIX.csv')
df_matrix.to_csv(out_csv, index=False)
print('Saved matrix to', out_csv)
