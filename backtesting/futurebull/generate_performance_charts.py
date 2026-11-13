#!/usr/bin/env python3
"""
================================================================================
7-YEAR PERFORMANCE CHARTS & BIDIRECTIONAL DASHBOARD GENERATOR
================================================================================
Directory   : backtesting/futurebull/
Role        : Generates interactive Plotly dark-theme HTML tearsheet and charts:
                - 7-Year Cumulative Equity Curve (Bidirectional vs Long-Only vs Short-Only)
                - Underwater Drawdown Profiles
                - Yearly PnL Breakdown (Long Contribution vs Short Contribution)
                - Win Rate & Expectancy Heatmaps
Outputs:
  - reports/PERFORMANCE_DASHBOARD.html
================================================================================
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    sys.exit("Error: plotly not installed.")

REPORTS_DIR = CURRENT_DIR / "reports"


def generate_dashboard():
    print("================================================================================")
    print("📊 GENERATING 7-YEAR BIDIRECTIONAL RESEARCH DASHBOARD & CHARTS")
    print("================================================================================")

    bidi_file = REPORTS_DIR / "BIDIRECTIONAL_7YR_ALL_TRADES.csv"
    yearly_file = REPORTS_DIR / "BIDIRECTIONAL_7YR_YEARLY_BREAKDOWN.csv"
    comp_file = REPORTS_DIR / "LONG_VS_SHORT_COMPARISON.csv"
    corr_file = REPORTS_DIR / "PHASE3_CORRELATION_MATRIX.csv"

    bidi_df = pd.read_csv(bidi_file) if bidi_file.exists() else pd.DataFrame()
    yearly_df = pd.read_csv(yearly_file) if yearly_file.exists() else pd.DataFrame()
    comp_df = pd.read_csv(comp_file) if comp_file.exists() else pd.DataFrame()
    corr_df = pd.read_csv(corr_file, index_col=0) if corr_file.exists() else pd.DataFrame()

    fig = make_subplots(
        rows=3, cols=2,
        subplot_titles=(
            "7-Year Cumulative Portfolio Equity (Long vs Short vs Bidirectional)",
            "Underwater Drawdown (%)",
            "Yearly Net PnL (Long vs Short Contribution)",
            "Long vs Short Performance Comparison",
            "Top Indicator Correlation Matrix",
            "Yearly Win Rate & Trade Count"
        ),
        specs=[
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "heatmap"}, {"type": "xy"}]
        ],
        vertical_spacing=0.10,
        horizontal_spacing=0.08
    )

    initial_cap = 2500000.0

    if not bidi_df.empty:
        bidi_df["entry_date"] = pd.to_datetime(bidi_df["entry_date"])
        bidi_df = bidi_df.sort_values("entry_date").reset_index(drop=True)

        # Combined Equity
        bidi_df["cum_net"] = bidi_df["net_pnl"].cumsum()
        bidi_df["cum_equity"] = initial_cap + bidi_df["cum_net"]
        bidi_df["peak"] = bidi_df["cum_equity"].cummax()
        bidi_df["dd"] = (bidi_df["cum_equity"] - bidi_df["peak"]) / bidi_df["peak"] * 100.0

        # Long Equity
        long_sub = bidi_df[bidi_df["direction"] == "LONG"].copy().reset_index(drop=True)
        long_sub["cum_equity"] = initial_cap + long_sub["net_pnl"].cumsum()

        # Short Equity
        short_sub = bidi_df[bidi_df["direction"] == "SHORT"].copy().reset_index(drop=True)
        short_sub["cum_equity"] = initial_cap + short_sub["net_pnl"].cumsum()

        fig.add_trace(go.Scatter(x=bidi_df["entry_date"], y=bidi_df["cum_equity"], name="Bidirectional (Total)", line=dict(color="#00E676", width=2.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=long_sub["entry_date"], y=long_sub["cum_equity"], name="Long-Only", line=dict(color="#2979FF", width=1.5, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=short_sub["entry_date"], y=short_sub["cum_equity"], name="Short-Only", line=dict(color="#FF9100", width=1.5, dash="dot")), row=1, col=1)

        fig.add_trace(go.Scatter(x=bidi_df["entry_date"], y=bidi_df["dd"], name="Drawdown %", line=dict(color="#FF5252", width=1.5)), row=1, col=2)

    # 2. Yearly PnL Stacked/Grouped Bars
    if not yearly_df.empty:
        fig.add_trace(go.Bar(x=yearly_df["year"], y=yearly_df["long_pnl_inr"], name="Long PnL", marker_color="#2979FF"), row=2, col=1)
        fig.add_trace(go.Bar(x=yearly_df["year"], y=yearly_df["short_pnl_inr"], name="Short PnL", marker_color="#FF9100"), row=2, col=1)

    # 3. Long vs Short Metrics
    if not comp_df.empty:
        fig.add_trace(go.Bar(x=comp_df["segment"], y=comp_df["total_net_pnl_inr"], name="Net PnL by Segment", marker_color=["#2979FF", "#FF9100", "#00E676"]), row=2, col=2)

    # 4. Correlation Heatmap
    if not corr_df.empty:
        top_cols = list(corr_df.columns[:14])
        sub_corr = corr_df.loc[top_cols, top_cols]
        fig.add_trace(go.Heatmap(z=sub_corr.values, x=top_cols, y=top_cols, colorscale="Viridis", showscale=False), row=3, col=1)

    # 5. Yearly Win Rate
    if not yearly_df.empty:
        fig.add_trace(go.Scatter(x=yearly_df["year"], y=yearly_df["win_rate_pct"], name="Win Rate %", mode="lines+markers", line=dict(color="#00E5FF", width=2)), row=3, col=2)

    fig.update_layout(
        template="plotly_dark",
        title_text="FUTURES BULL & BEAR BREAKOUT SCANNER — 7-YEAR (2019-2026) NFO PERFORMANCE DASHBOARD",
        height=1250,
        showlegend=True,
        paper_bgcolor="#121212",
        plot_bgcolor="#1e1e1e",
        font=dict(family="SF Pro Display, Arial, sans-serif", size=11, color="#E0E0E0")
    )

    out_html = REPORTS_DIR / "PERFORMANCE_DASHBOARD.html"
    fig.write_html(str(out_html))
    print(f"✓ Updated Dashboard exported successfully to: {out_html}")
    print("================================================================================\n")


if __name__ == "__main__":
    generate_dashboard()
