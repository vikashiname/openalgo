# backtest.py
# Entry point wrapper for the optimized Ichimoku TK Crossover backtest strategy
# Implements experienced trader filters to reduce sideways whipsaws.

from ichimoku_tk_crossover import IchimokuTKBacktester

if __name__ == "__main__":
    print("🚀 Running optimized Ichimoku TK Crossover Backtest (1-Year)...")
    
    # Instantiate the backtester with the recommended high-grade MCX / Positional settings
    backtester = IchimokuTKBacktester(
        symbol="RELIANCE.NS",
        period="1y",
        interval="1d",
        capital=100000.0,
        risk_per_trade=0.015,         # 1.5% Risk per trade
        risk_reward_ratio=2.5,         # 2.5x Target
        
        # Professional Filters
        use_cloud_filter=True,          # Price must be above/below cloud
        use_future_cloud_filter=True,   # Future cloud must be supportive
        use_cloud_thickness_filter=True,# Avoid entry on thin flat clouds
        cloud_thickness_pct=0.008,      # 0.8% minimum thickness threshold
        use_macd_filter=True,           # MACD state filter (trend support)
        use_macd_cross=False,           # Disable recent crossover restriction
        
        # Advanced Risk Management
        stop_loss_type="atr",           # Volatility-based stop loss
        atr_mult=2.0,                   # 2x ATR stop distance
        trail_sl=True,                  # Trailing stop loss enabled
        exit_on_opposite_cross=True,    # Exit trade on opposite crossover
        
        enable_shorts=True
    )
    
    # Run the backtester
    backtester.run(html_filename="ichimoku_dashboard.html")
    
    print("\n💡 Optimization Run Complete.")
    print("Check the generated 'ichimoku_dashboard.html' in your browser for the full interactive charts.")
