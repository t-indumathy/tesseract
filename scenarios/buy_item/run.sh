#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT_DIR"

echo "==========================================================="
echo " Tesseract — UCP + AP2 Buy Item Scenario"
echo "==========================================================="
echo ""

# Check uv is available
if ! command -v uv &> /dev/null; then
    echo "[ERROR] 'uv' not found. Install from https://github.com/astral-sh/uv"
    exit 1
fi

# Install dependencies silently
echo "[setup] Installing dependencies..."
uv sync --quiet

# Start merchant server in background
echo "[server] Starting UCP merchant server on :8080..."
uv run uvicorn src.merchant.server:app --port 8080 --log-level warning &
SERVER_PID=$!
trap "kill $SERVER_PID 2>/dev/null" EXIT

# Wait for server to be ready
sleep 2

# Run the demo flow
echo "[agent] Running shopping agent demo flow..."
echo ""
uv run python src/agent/shopping_agent.py demo

echo ""
echo "[done] Scenario complete."
