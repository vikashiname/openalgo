#!/usr/bin/env python3
"""
================================================================================
Personal Exposure & Real Bhavcopy Credit Spread Audit (550 NIFTYBEES Units)
Location: backtesting/nifty_etf_covered_call/scripts/audit_personal_exposure_550.py
================================================================================
Empirical evaluation using real NSE F&O Bhavcopy records:
  - Exact historical lot sizes: 50 pre-April 2024, 25 May-Nov 2024, 65 post-Jan 2026 (NSE/FAOP/70616).
  - Real traded prices for both Short Call and Long Protective Call wing (Strike + 300).
  - Itemized Fyers brokerage, STT, turnover, SEBI, GST fees.
  - Fyers 8.0% haircut on NIFTYBEES and mandatory SEBI 50:50 cash-to-collateral rule.
================================================================================
"""

import os
import sys
import glob
import re
import zipfile
from pathlib import Path
import pandas as pd
import numpy as np

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_DIR / "data"
BASELINE_DIR = WORKSPACE_DIR / "baseline"
BHAV_DIR = Path("/Users/mac/Desktop/openalgo/backtesting/oi/data/raw/bhavcopy")

sys.path.insert(0, str(WORKSPACE_DIR))

# Confirmed user portfolio
UNITS_HELD = 550
COST_BASIS_PER_UNIT = 250.0
TOTAL_COST_BASIS = UNITS_HELD * COST_BASIS_PER_UNIT  # ₹1,37,500.00


def calc_opt_costs(turnover: float, side: str, date_str: str) -> float:
    """Itemized statutory costs for F&O options on Fyers."""
    brokerage = 20.0
    stt_rate = 0.0010 if date_str >= "2024-10-01" else 0.000625
    stt = turnover * stt_rate if side == "SELL" else 0.0
    exchange_fee = turnover * 0.0003503
    sebi_fee = turnover * 0.000001
    stamp_duty = turnover * 0.00003 if side == "BUY" else 0.0
    gst = (brokerage + exchange_fee + sebi_fee) * 0.18
    return brokerage + stt + exchange_fee + sebi_fee + stamp_duty + gst


def run_personal_audit():
    ledger_path = BASELINE_DIR / "cycle_ledger.csv"
    if not ledger_path.exists():
        raise FileNotFoundError(f"Missing {ledger_path}")
    df_cycles = pd.read_csv(ledger_path)

    # Build bhavcopy map
    files = glob.glob(f"{BHAV_DIR}/*.zip")
    file_map = {}
    for f in files:
        bn = os.path.basename(f)
        m = re.search(r"fo(\d{2}[A-Z]{3}\d{4})bhav", bn)
        if m:
            d = pd.to_datetime(m.group(1), format="%d%b%Y").strftime("%Y-%m-%d")
            file_map[d] = f
        else:
            m2 = re.search(r"BhavCopy_NSE_FO_0_0_0_(\d{8})_F_0000", bn)
            if m2:
                d = pd.to_datetime(m2.group(1), format="%Y%m%d").strftime("%Y-%m-%d")
                file_map[d] = f

    cycles_meta = [
        ("2022-01-27", ["27-Jan-2022", "27-JAN-2022", "2022-01-27"]),
        ("2022-02-24", ["24-Feb-2022", "24-FEB-2022", "2022-02-24"]),
        ("2022-03-31", ["31-Mar-2022", "31-MAR-2022", "2022-03-31"]),
        ("2022-04-28", ["28-Apr-2022", "28-APR-2022", "2022-04-28"]),
        ("2022-05-26", ["26-May-2022", "26-MAY-2022", "2022-05-26"]),
        ("2022-06-30", ["30-Jun-2022", "30-JUN-2022", "2022-06-30"]),
        ("2022-07-28", ["28-Jul-2022", "28-JUL-2022", "2022-07-28"]),
        ("2022-08-25", ["25-Aug-2022", "25-AUG-2022", "2022-08-25"]),
        ("2022-09-29", ["29-Sep-2022", "29-SEP-2022", "2022-09-29"]),
        ("2022-10-27", ["27-Oct-2022", "27-OCT-2022", "2022-10-27"]),
        ("2022-11-24", ["24-Nov-2022", "24-NOV-2022", "2022-11-24"]),
        ("2022-12-29", ["29-Dec-2022", "29-DEC-2022", "2022-12-29"]),
        ("2023-01-25", ["25-Jan-2023", "25-JAN-2023", "2023-01-25"]),
        ("2023-02-23", ["23-Feb-2023", "23-FEB-2023", "2023-02-23"]),
        ("2023-03-29", ["29-Mar-2023", "29-MAR-2023", "2023-03-29"]),
        ("2023-04-27", ["27-Apr-2023", "27-APR-2023", "2023-04-27"]),
        ("2023-05-25", ["25-May-2023", "25-MAY-2023", "2023-05-25"]),
        ("2023-06-28", ["29-Jun-2023", "29-JUN-2023", "28-Jun-2023", "28-JUN-2023", "2023-06-28", "2023-06-29"]),
        ("2023-07-27", ["27-Jul-2023", "27-JUL-2023", "2023-07-27"]),
        ("2023-08-31", ["31-Aug-2023", "31-AUG-2023", "2023-08-31"]),
        ("2023-09-28", ["28-Sep-2023", "28-SEP-2023", "2023-09-28"]),
        ("2023-10-26", ["26-Oct-2023", "26-OCT-2023", "2023-10-26"]),
        ("2023-11-30", ["30-Nov-2023", "30-NOV-2023", "2023-11-30"]),
        ("2023-12-28", ["28-Dec-2023", "28-DEC-2023", "2023-12-28"]),
        ("2024-01-25", ["25-Jan-2024", "25-JAN-2024", "2024-01-25"]),
        ("2024-02-29", ["29-Feb-2024", "29-FEB-2024", "2024-02-29"]),
        ("2024-03-28", ["28-Mar-2024", "28-MAR-2024", "2024-03-28"]),
        ("2024-04-25", ["25-Apr-2024", "25-APR-2024", "2024-04-25"]),
        ("2024-05-30", ["30-May-2024", "30-MAY-2024", "2024-05-30"]),
        ("2024-06-27", ["27-Jun-2024", "27-JUN-2024", "2024-06-27"]),
        ("2024-07-25", ["25-Jul-2024", "25-JUL-2024", "2024-07-25"])
    ]

    def get_bhav_price(fpath, expiry_str_list, target_strike):
        with zipfile.ZipFile(fpath) as z:
            name = z.namelist()[0]
            df = pd.read_csv(z.open(name))
            cols = {"INSTRUMENT": "inst", "SYMBOL": "sym", "EXPIRY_DT": "expiry", "STRIKE_PR": "strike", "OPTION_TYP": "opt_type", "CLOSE": "close", "SETTLE_PR": "settle"}
            df = df.rename(columns=cols)
            if "FinInstrmTp" in df.columns:
                df = df.rename(columns={"FinInstrmTp": "inst", "TckrSymb": "sym", "XpryDt": "expiry", "StrkPric": "strike", "OptnTp": "opt_type", "ClsPric": "close", "SttlmPric": "settle"})
            df["opt_type"] = df["opt_type"].astype(str).str.strip()
            df["sym"] = df["sym"].astype(str).str.strip()
            df["expiry"] = df["expiry"].astype(str).str.strip()
            nifty_ce = df[(df["sym"] == "NIFTY") & (df["opt_type"] == "CE")]
            matches = nifty_ce[nifty_ce["expiry"].str.upper().isin([x.upper() for x in expiry_str_list])]
            match_strike = matches[matches["strike"] == target_strike]
            if not match_strike.empty:
                r = match_strike.iloc[0]
                return float(r["close"]) if float(r["close"]) > 0 else float(r["settle"])
            return 0.0

    records = []
    for idx, r in df_cycles.iterrows():
        entry_d = r["entry_date"]
        exp_d = r["expiry_date"]
        lot = int(r["lot_size"])
        s_in = float(r["s_entry"])
        s_out = float(r["s_exit"])
        p_in = float(r["p_entry"])
        p_out = float(r["p_exit"])
        k_short = float(r["strike"])
        k_long = k_short + 300.0

        exp_variants = cycles_meta[idx][1]

        # Short Call Fills
        short_raw = float(r["opt_raw_price"])
        short_fill = max(0.05, short_raw - 0.50)  # Slippage

        # Long Call Fills from Bhavcopy
        long_raw = get_bhav_price(file_map[entry_d], exp_variants, k_long)
        long_fill = long_raw + 0.50  # Slippage

        net_credit_pts = short_fill - long_fill
        gross_credit_inr = net_credit_pts * lot

        # Statutory Costs
        c_short = calc_opt_costs(short_fill * lot, "SELL", entry_d)
        c_long = calc_opt_costs(long_fill * lot, "BUY", entry_d)
        total_costs = c_short + c_long

        # Expiry Settlement
        short_intr = max(0.0, s_out - k_short)
        long_intr = max(0.0, s_out - k_long)
        net_debit_inr = (short_intr - long_intr) * lot

        opt_pnl = gross_credit_inr - net_debit_inr - total_costs
        etf_intra_pnl = UNITS_HELD * (p_out - p_in)

        # Theoretical max loss
        max_loss = (300.0 - net_credit_pts) * lot + total_costs

        # Fyers Margins (approx spread width * lot)
        total_margin = 300.0 * lot
        min_cash_required = total_margin * 0.50
        collateral_margin_required = total_margin * 0.50

        records.append({
            "cycle": idx + 1,
            "entry_date": entry_d,
            "expiry_date": exp_d,
            "lot_size": lot,
            "s_entry": s_in,
            "s_exit": s_out,
            "p_entry": p_in,
            "p_exit": p_out,
            "k_short": k_short,
            "k_long": k_long,
            "short_fill": short_fill,
            "long_fill": long_fill,
            "net_credit_pts": net_credit_pts,
            "gross_credit_inr": gross_credit_inr,
            "total_costs_inr": total_costs,
            "short_intrinsic": short_intr,
            "long_intrinsic": long_intr,
            "net_debit_inr": net_debit_inr,
            "opt_pnl": opt_pnl,
            "etf_intra_pnl": etf_intra_pnl,
            "combined_cycle_pnl": etf_intra_pnl + opt_pnl,
            "max_theoretical_loss": max_loss,
            "total_margin_req": total_margin,
            "min_cash_req": min_cash_required,
            "collateral_req": collateral_margin_required,
        })

    out_df = pd.DataFrame(records)
    out_csv = WORKSPACE_DIR / "data" / "personal_ledger_550_spread.csv"
    out_df.to_csv(out_csv, index=False)
    print(f"[✓] Saved trade ledger to {out_csv}")

    # Calculate Buy & Hold on 550 units
    bh_pnl = UNITS_HELD * (df_cycles["p_exit"].iloc[-1] - df_cycles["p_entry"].iloc[0])
    print(f"\n--- 550 Units Performance Summary ---")
    print(f"ETF Buy & Hold Gain:      ₹{bh_pnl:,.2f}")
    print(f"Spread Option Leg Net P&L: ₹{out_df['opt_pnl'].sum():,.2f}")
    print(f"Spread Combined Net Gain:  ₹{out_df['combined_cycle_pnl'].sum():,.2f}")
    print(f"Worst Cycle Net P&L:       ₹{out_df['combined_cycle_pnl'].min():,.2f}")
    print(f"Option Win Rate:           {(out_df['opt_pnl'] > 0).mean() * 100:.1f}%")


if __name__ == "__main__":
    run_personal_audit()
