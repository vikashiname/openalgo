#!/usr/bin/env bash
# scripts/install_daily_maintenance.sh
# One-command installer to automatically schedule daily system space & RAM optimization on AWS/Linux.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CLEANUP_SCRIPT="$SCRIPT_DIR/maintenance_cleanup.sh"
CRON_FILE="/etc/cron.d/openalgo_daily_maintenance"

echo "=== OpenAlgo Automatic Daily Maintenance Setup ==="

if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "[!] Non-Linux system detected. Cron service installation is intended for Linux/Ubuntu servers."
    exit 0
fi

# Ensure cleanup script is executable
chmod +x "$CLEANUP_SCRIPT"

# Detect root / sudo
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        echo "[!] Root privileges or sudo required to install system cron."
        exit 1
    fi
fi

# Determine execution time (Daily at 23:30 / 11:30 PM local server time)
CRON_SCHEDULE="30 23 * * *"

echo "[*] Installing automated daily cron job to $CRON_FILE..."
$SUDO bash -c "cat <<EOF > $CRON_FILE
# /etc/cron.d/openalgo_daily_maintenance
# Automatically created by OpenAlgo maintenance installer
# Runs daily at 23:30 to optimize disk space, prune logs, vacuum databases, and flush RAM.
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

$CRON_SCHEDULE root $CLEANUP_SCRIPT > /dev/null 2>&1
EOF"

$SUDO chmod 644 "$CRON_FILE"

# Restart cron daemon to load new configuration
if command -v systemctl &>/dev/null; then
    $SUDO systemctl restart cron 2>/dev/null || $SUDO systemctl restart crond 2>/dev/null || true
elif command -v service &>/dev/null; then
    $SUDO service cron restart 2>/dev/null || true
fi

echo "[✓] Automated daily maintenance successfully installed!"
echo "[*] Schedule: Every day at 23:30"
echo "[*] Script   : $CLEANUP_SCRIPT"
echo "[*] Log file : /home/ubuntu/maintenance.log"

# Run once immediately to optimize current space
echo ""
echo "[*] Running initial optimization run now..."
$SUDO "$CLEANUP_SCRIPT" || true
echo "[✓] Initial optimization complete. System is ready."
