#!/usr/bin/env python3
"""
================================================================================
OpenAlgo Quantitative Research Engine Launcher
================================================================================
Executes the full 12-phase research study across CL=F, BZ=F, GC=F, SI=F, NG=F.
"""

from research.reports.generate_report import run_comprehensive_study

if __name__ == "__main__":
    run_comprehensive_study()
