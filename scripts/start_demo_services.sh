#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
mkdir -p logs runtime

DB_PATH="${AER_DB_PATH:-$PWD/runtime/aer_loop_model_smoke_9728967_full_debug.sqlite}"
API_PORT="${AER_API_PORT:-18081}"
OPENCLAW_PORT="${AER_OPENCLAW_PORT:-18891}"
API_PID="runtime/api_${API_PORT}.pid"
OPENCLAW_PID="runtime/openclaw_gateway_${OPENCLAW_PORT}.pid"

if [[ ! -f "$DB_PATH" ]]; then
  echo "database not found: $DB_PATH" >&2
  exit 1
fi

if [[ ! -f "$API_PID" ]] || ! ps -p "$(cat "$API_PID")" >/dev/null 2>&1; then
  nohup env AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-fallback}" AER_DB_PATH="$DB_PATH" AER_API_PORT="$API_PORT" \
    scripts/start_api.sh > "logs/api_${API_PORT}.log" 2>&1 < /dev/null &
  echo $! > "$API_PID"
fi

sleep 2
curl -fsS "http://127.0.0.1:${API_PORT}/api/dashboard" >/dev/null

if [[ ! -f "$OPENCLAW_PID" ]] || ! ps -p "$(cat "$OPENCLAW_PID")" >/dev/null 2>&1; then
  nohup env AER_BACKEND_URL="http://127.0.0.1:${API_PORT}" AER_OPENCLAW_PORT="$OPENCLAW_PORT" \
    scripts/start_openclaw_gateway.sh > "logs/openclaw_gateway_${OPENCLAW_PORT}.log" 2>&1 < /dev/null &
  echo $! > "$OPENCLAW_PID"
fi

sleep 3
echo "api_pid=$(cat "$API_PID") api_url=http://127.0.0.1:${API_PORT}"
echo "openclaw_pid=$(cat "$OPENCLAW_PID") openclaw_url=http://127.0.0.1:${OPENCLAW_PORT}"
