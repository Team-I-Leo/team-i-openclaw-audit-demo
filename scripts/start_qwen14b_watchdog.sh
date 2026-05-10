#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="/hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510"
WD="/hpc2hdd/home/hqi881/tools/codex/hpc2_hf_watchdog_download.sh"
LOGDIR="$PROJECT_ROOT/logs/watchdog_downloads"
TARGET="$PROJECT_ROOT/models/Qwen2.5-Coder-14B-Instruct"
LOG="$LOGDIR/qwen25_coder_14b_watchdog.log"
PID="$LOGDIR/qwen25_coder_14b_watchdog.pid"

mkdir -p "$LOGDIR" "$TARGET"

if [[ ! -x "$WD" ]]; then
  echo "watchdog script missing or not executable: $WD" >&2
  exit 1
fi

if [[ -f "$PID" ]] && ps -p "$(cat "$PID")" >/dev/null 2>&1; then
  echo "qwen25_coder_14b_watchdog already running: $(cat "$PID")"
  exit 0
fi

(
  export REPO_ID="Qwen/Qwen2.5-Coder-14B-Instruct"
  export TARGET_DIR="$TARGET"
  export HF_HOME_DIR="/hpc2hdd/home/hqi881/hf_home"
  export STALL_SECONDS=600
  export CHECK_SECONDS=60
  export RETRY_SLEEP_SECONDS=30
  export MAX_WORKERS=1
  export HF_HUB_ENABLE_HF_TRANSFER=0
  export HF_HUB_DISABLE_XET=1
  exec "$WD"
) >> "$LOG" 2>&1 < /dev/null &

echo $! > "$PID"
echo "started qwen25_coder_14b_watchdog pid=$(cat "$PID") target=$TARGET log=$LOG"
