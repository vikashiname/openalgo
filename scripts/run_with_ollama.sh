#!/usr/bin/env bash
# -------------------------------------------------------------------
# Run Antigravity (agy) with the local Ollama model (llama3)
# -------------------------------------------------------------------
# This script ensures the Ollama server is running and then invokes
# the `agy` CLI, forcing it to use the custom Ollama provider you
# configured in ~/.antigravity/settings.json.
# -------------------------------------------------------------------
set -euo pipefail

# 1️⃣ Ensure Ollama server is running (background daemon).
# If it's already running the command will fail harmlessly, so we
# suppress errors.
if ! pgrep -x ollama > /dev/null 2>&1; then
  echo "Starting Ollama server..."
  # Launch in background; output goes to a log file.
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  # Give it a moment to start.
  sleep 2
else
  echo "Ollama server already running."
fi

# 2️⃣ Run agy with the Ollama model.
# The model name must match the provider entry "ollama (llama3)"
# as defined in ~/.antigravity/settings.json.

# Pass any arguments after the script to agy.
# Example: ./run_with_ollama.sh -p "Explain recursion."

agy --model "ollama (llama3)" "$@"
