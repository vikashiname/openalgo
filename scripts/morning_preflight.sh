#!/usr/bin/env bash
# scripts/morning_preflight.sh
# Automated Morning Market-Open Pre-Flight Checklist for OpenAlgo
# Can be executed locally on Mac (tests AWS via SSH) or directly on the AWS server.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

AWS_HOST="${AWS_HOST:-13.203.187.139}"
AWS_USER="${AWS_USER:-ubuntu}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/openalgo-key.pem}"

echo "================================================================================"
echo "🌅  OPENALGO MORNING MARKET-OPEN PRE-FLIGHT VERIFICATION (09:00 IST GATE)"
echo "================================================================================"
echo "• Target Host : $AWS_HOST (vikashiname.in)"
echo "• Timestamp   : $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "================================================================================"

# If running directly on the AWS instance
if [ -d "/home/ubuntu/fyersawsog" ] && [ "$(hostname -I 2>/dev/null | grep -c '172.31' || true)" -gt 0 ]; then
    echo "[*] Detected execution DIRECTLY on AWS production server."
    APP_DIR="/home/ubuntu/fyersawsog"
    PYTHON="$APP_DIR/venv/bin/python"

    echo ""
    echo "[1/4] Checking OpenAlgo Systemd Service..."
    systemctl is-active --quiet openalgo.service && echo "  ✅ openalgo.service is ACTIVE & RUNNING" || echo "  ❌ openalgo.service is DOWN"

    echo ""
    echo "[2/4] Verifying Broker Session & Market Feeds (testopen.py)..."
    $PYTHON "$APP_DIR/strategies/liveonopenalgo/testopen.py" --dry-run --telegram || true

    echo ""
    echo "[3/4] Checking Scheduled Strategies in strategy_configs.json..."
    $PYTHON -c "
import json
with open('$APP_DIR/strategies/strategy_configs.json') as f:
    cfg = json.load(f)
for sid, s in cfg.items():
    name = s.get('name', sid)
    sched = '✅ Scheduled' if s.get('is_scheduled') else '⏸️ Unscheduled'
    stopped = '⚠️ Stopped' if s.get('manually_stopped') else '🟢 Ready'
    window = f\"{s.get('schedule_start', '09:00')}-{s.get('schedule_stop', '16:00')}\"
    print(f'  • {name:<25} | {sched} | {stopped} | Window: {window}')
"

    echo ""
    echo "[4/4] Checking Server Resource Telemetry..."
    df -h / | awk 'NR==2 {print "  • Disk Usage : " $3 " used / " $4 " available (" $5 ")"}'
    free -h | awk 'NR==2 {print "  • RAM Usage  : " $3 " used / " $7 " available"}'
    exit 0
fi

# If running remotely from Mac via SSH
if [ -f "$SSH_KEY" ]; then
    echo "[*] Connecting to AWS via SSH ($AWS_USER@$AWS_HOST)..."
    ssh -i "$SSH_KEY" -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new "$AWS_USER@$AWS_HOST" bash -s << 'EOF'
APP_DIR="/home/ubuntu/fyersawsog"
PYTHON="$APP_DIR/venv/bin/python"

echo ""
echo "[1/4] Checking OpenAlgo Systemd Service..."
systemctl is-active --quiet openalgo.service && echo "  ✅ openalgo.service is ACTIVE & RUNNING" || echo "  ❌ openalgo.service is DOWN"

echo ""
echo "[2/4] Verifying Broker Session & Market Feeds (testopen.py)..."
$PYTHON "$APP_DIR/strategies/liveonopenalgo/testopen.py" --dry-run --telegram || true

echo ""
echo "[3/4] Checking Scheduled Strategies in strategy_configs.json..."
$PYTHON -c "
import json
with open('$APP_DIR/strategies/strategy_configs.json') as f:
    cfg = json.load(f)
for sid, s in cfg.items():
    name = s.get('name', sid)
    sched = '✅ Scheduled' if s.get('is_scheduled') else '⏸️ Unscheduled'
    stopped = '⚠️ Stopped' if s.get('manually_stopped') else '🟢 Ready'
    window = f\"{s.get('schedule_start', '09:00')}-{s.get('schedule_stop', '16:00')}\"
    print(f'  • {name:<25} | {sched} | {stopped} | Window: {window}')
"

echo ""
echo "[4/4] Checking Server Resource Telemetry..."
df -h / | awk 'NR==2 {print "  • Disk Usage : " $3 " used / " $4 " available (" $5 ")"}'
free -h | awk 'NR==2 {print "  • RAM Usage  : " $3 " used / " $7 " available"}'
EOF
else
    echo "❌ SSH Key not found at $SSH_KEY. Please specify SSH_KEY path."
    exit 1
fi

echo ""
echo "================================================================================"
echo "📋 PRE-FLIGHT AUDIT COMPLETE"
echo "================================================================================"
