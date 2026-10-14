import pandas as pd
import numpy as np

def compute_underlying_features(df):
    """
    Computes daily underlying spot features, EMAs, Realized Volatility,
    ATM IV, and IV Percentile (IVP).
    df: options DataFrame containing ['trade_date', 'underlying_price', 'expiry_date', 'strike', 'option_type', 'settle_price']
    """
    # 1. Daily unique underlying price
    daily = df.groupby('trade_date')['underlying_price'].first().reset_index()
    daily.rename(columns={'underlying_price': 'spot'}, inplace=True)
    daily = daily.sort_values('trade_date').reset_index(drop=True)

    # 2. Technical trend filters (50 EMA, 200 EMA)
    daily['ema_50'] = daily['spot'].ewm(span=50, adjust=False).mean()
    daily['ema_200'] = daily['spot'].ewm(span=200, adjust=False).mean()
    daily['trend_bullish'] = daily['spot'] > daily['ema_50']
    daily['macro_bullish'] = daily['spot'] > daily['ema_200']

    # 3. Realized Volatility (20-day rolling log returns)
    daily['log_ret'] = np.log(daily['spot'] / daily['spot'].shift(1))
    daily['realized_vol_20'] = daily['log_ret'].rolling(20).std() * np.sqrt(252.0)
    daily['realized_vol_20'] = daily['realized_vol_20'].bfill().fillna(0.18)

    # 4. ATM IV estimation from near-term options
    # Find ATM call option closest to 15-30 DTE for each trade_date
    df['dte'] = (pd.to_datetime(df['expiry_date']) - pd.to_datetime(df['trade_date'])).dt.days
    near_opts = df[(df['dte'] >= 7) & (df['dte'] <= 35) & (df['option_type'] == 'CE') & (df['settle_price'] > 1.0)].copy()
    
    if not near_opts.empty:
        near_opts['atm_dist'] = abs(near_opts['strike'] - near_opts['underlying_price'])
        # Pick the closest strike per trade_date
        closest_idx = near_opts.groupby('trade_date')['atm_dist'].idxmin()
        atm_sample = near_opts.loc[closest_idx].copy()
        
        # Approximate ATM IV using Brenner-Subrahmanyam formula: sigma ~ sqrt(2*pi/T) * (C / S)
        # C = ATM Call, S = Spot, T = dte / 365.0
        atm_sample['T'] = np.maximum(0.01, atm_sample['dte'] / 365.0)
        atm_sample['atm_iv'] = (atm_sample['settle_price'] / atm_sample['underlying_price']) * np.sqrt(2.0 * np.pi / atm_sample['T'])
        atm_map = dict(zip(atm_sample['trade_date'], atm_sample['atm_iv']))
        daily['atm_iv'] = daily['trade_date'].map(atm_map).fillna(daily['realized_vol_20'])
    else:
        daily['atm_iv'] = daily['realized_vol_20']

    # 5. 252-day IV Percentile (IVP)
    daily['iv_percentile'] = daily['atm_iv'].rolling(252, min_periods=30).apply(
        lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-6) * 100.0, raw=False
    ).fillna(50.0)

    return daily.set_index('trade_date')
