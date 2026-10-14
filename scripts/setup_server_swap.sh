#!/usr/bin/env bash
# scripts/setup_server_swap.sh
# Safeguard script to configure swap memory on Ubuntu/Linux cloud instances (AWS/GCP/Oracle/DigitalOcean)
# Prevents pyarrow.lib.ArrowMemoryError and OOM process terminations.

set -euo pipefail

SWAP_SIZE_GB="${1:-4}"
SWAP_FILE="/swapfile"

echo "=== System Memory & Swap Check ==="
free -h

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo "[!] Non-Linux OS detected ($OSTYPE). Swap configuration skipped."
    exit 0
fi

# Check existing swap
EXISTING_SWAP=$(swapon --show | wc -l)

if [ "$EXISTING_SWAP" -gt 1 ]; then
    echo "[✓] Swap is already active:"
    swapon --show
    echo "If you need more swap, expand or recreate $SWAP_FILE."
    exit 0
fi

echo "[*] No active swap found. Setting up ${SWAP_SIZE_GB}GB swap space..."

# Check if running as root or with sudo
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if command -v sudo &>/dev/null; then
        SUDO="sudo"
    else
        echo "[!] Error: Root privileges or sudo required to configure swap."
        exit 1
    fi
fi

# Allocate swap file
if [ ! -f "$SWAP_FILE" ]; then
    echo "[*] Creating $SWAP_FILE (${SWAP_SIZE_GB}G)..."
    $SUDO fallocate -l "${SWAP_SIZE_GB}G" "$SWAP_FILE" || $SUDO dd if=/dev/zero of="$SWAP_FILE" bs=1G count="$SWAP_SIZE_GB" status=progress
fi

$SUDO chmod 600 "$SWAP_FILE"
$SUDO mkswap "$SWAP_FILE"
$SUDO swapon "$SWAP_FILE"

# Persist across reboots in /etc/fstab
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "$SWAP_FILE none swap sw 0 0" | $SUDO tee -a /etc/fstab
    echo "[*] Added swap entry to /etc/fstab for persistence."
fi

# Adjust swappiness for backtesting workloads (default 60 -> 10 to prefer RAM)
$SUDO sysctl vm.swappiness=10 || true
if ! grep -q "vm.swappiness" /etc/sysctl.conf; then
    echo "vm.swappiness=10" | $SUDO tee -a /etc/sysctl.conf
fi

echo "=== Swap Configuration Complete ==="
free -h
