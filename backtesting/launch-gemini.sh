#!/usr/bin/env bash
# ==============================================================================
# OpenAlgo Backtesting - Gemini CLI YOLO Launcher
# ==============================================================================
# Purpose:
#   Launch Google Gemini CLI with `--approval-mode=yolo` for backtesting and
#   research workflows, allowing auto-approval of Python data-processing and
#   backtest execution without repeated confirmation prompts.
#
# Safety Guarantee:
#   Enforces execution within ~/Desktop/openalgo/backtesting to prevent
#   unrestricted execution in root/live trading environments.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
CURRENT_DIR="$(pwd -P)"

# Safety check: Ensure execution stays within the backtesting directory tree
case "$CURRENT_DIR" in
  "$SCRIPT_DIR"* )
    TARGET_DIR="$CURRENT_DIR"
    ;;
  * )
    echo "[Notice] Switching working directory to backtesting workspace:"
    echo "  $SCRIPT_DIR"
    cd "$SCRIPT_DIR"
    TARGET_DIR="$SCRIPT_DIR"
    ;;
esac

echo "=========================================================="
echo " Gemini CLI Backtesting & Research Launcher"
echo " Working Dir   : $TARGET_DIR"
echo " Approval Mode : yolo (--approval-mode=yolo)"
echo "=========================================================="

exec gemini --approval-mode=yolo "$@"
