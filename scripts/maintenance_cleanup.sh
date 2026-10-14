#!/bin/bash
# OpenAlgo AWS EC2 Automated Daily & Weekly Maintenance Script
# Purpose: Reclaims disk space, vacuums databases, purges temporary cache, and flushes RAM.

set -e

LOG_FILE="/home/ubuntu/maintenance.log"
APP_DIR="/home/ubuntu/fyersawsog"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting system space & memory maintenance..." >> "$LOG_FILE"

# 1. Vacuum systemd journal logs (keep max 30MB or 3 days)
if command -v journalctl &>/dev/null; then
    journalctl --vacuum-size=30M --vacuum-time=3d >> "$LOG_FILE" 2>&1 || true
fi

# 2. Clean rotated and compressed system logs
find /var/log -type f \( -name "*.gz" -o -name "*.[0-9]" -o -name "*.old" \) -delete 2>> "$LOG_FILE" || true

# 3. Clean Apt package cache & orphaned packages (if sudo available)
if command -v apt-get &>/dev/null; then
    apt-get clean >> "$LOG_FILE" 2>&1 || true
    apt-get -y autoremove --purge >> "$LOG_FILE" 2>&1 || true
fi

# 4. Clean temporary Python files (__pycache__, .pytest_cache, core dumps)
if [ -d "$APP_DIR" ]; then
    find "$APP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$APP_DIR" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find "$APP_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.pyd" -o -name "core.*" \) -delete 2>/dev/null || true
    find /tmp -type f -atime +2 -delete 2>/dev/null || true
fi

# 5. Rotate/Truncate large application log files (>10MB)
LOG_DIR="$APP_DIR/log"
if [ -d "$LOG_DIR" ]; then
    for f in "$LOG_DIR"/*.log "$LOG_DIR"/*.jsonl; do
        if [ -f "$f" ]; then
            FILE_SIZE=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
            if [ "$FILE_SIZE" -gt 10485760 ]; then
                tail -n 2000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] Truncated oversized log: $(basename "$f") (${FILE_SIZE} bytes)" >> "$LOG_FILE"
            fi
        fi
    done
fi

# 6. Prune and optimize SQLite databases
DB_DIR="$APP_DIR/db"
if [ -d "$DB_DIR" ] && command -v sqlite3 &>/dev/null; then
    # health.db (keep 2 days)
    if [ -f "$DB_DIR/health.db" ]; then
        sqlite3 "$DB_DIR/health.db" "
        CREATE INDEX IF NOT EXISTS idx_health_metrics_timestamp ON health_metrics(timestamp);
        CREATE INDEX IF NOT EXISTS idx_health_alerts_timestamp ON health_alerts(timestamp);
        DELETE FROM health_metrics WHERE timestamp < datetime('now', '-2 days');
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        VACUUM;
        " >> "$LOG_FILE" 2>&1 || true
    fi

    # logs.db (keep 5 days)
    if [ -f "$DB_DIR/logs.db" ]; then
        sqlite3 "$DB_DIR/logs.db" "
        DELETE FROM traffic_logs WHERE timestamp < datetime('now', '-5 days');
        DELETE FROM error_404_tracker WHERE last_error_at < datetime('now', '-5 days');
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        VACUUM;
        " >> "$LOG_FILE" 2>&1 || true
    fi

    # latency.db (keep 7 days)
    if [ -f "$DB_DIR/latency.db" ]; then
        sqlite3 "$DB_DIR/latency.db" "
        CREATE INDEX IF NOT EXISTS idx_order_latency_timestamp ON order_latency(timestamp);
        CREATE INDEX IF NOT EXISTS idx_order_latency_order_id ON order_latency(order_id);
        DELETE FROM order_latency WHERE timestamp < datetime('now', '-7 days');
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        VACUUM;
        " >> "$LOG_FILE" 2>&1 || true
    fi

    # Checkpoint WAL logs for openalgo.db
    if [ -f "$DB_DIR/openalgo.db" ]; then
        sqlite3 "$DB_DIR/openalgo.db" "PRAGMA wal_checkpoint(TRUNCATE);" >> "$LOG_FILE" 2>&1 || true
    fi
fi

# 7. Flush Linux page cache and reclaim RAM
sync
if [ -w /proc/sys/vm/drop_caches ]; then
    echo 3 > /proc/sys/vm/drop_caches
fi

# 8. Log final status
AVAIL_DISK=$(df -h / | awk 'NR==2 {print $4}')
USE_PERCENT=$(df -h / | awk 'NR==2 {print $5}')
AVAIL_MEM=$(free -h 2>/dev/null | awk '/Mem:/ {print $7}' || echo "N/A")
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Maintenance complete. Free disk: $AVAIL_DISK ($USE_PERCENT used) | Free memory: $AVAIL_MEM" >> "$LOG_FILE"

