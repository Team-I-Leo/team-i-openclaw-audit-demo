#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
export AER_RUN_ID="${AER_RUN_ID:-${SLURM_JOB_ID:-quick}}"
export AER_DB_PATH="${AER_DB_PATH:-$AER_PROJECT_ROOT/runtime/aer_loop_model_quick_${AER_RUN_ID}.sqlite}"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-local}"
export AER_MODEL_PATH_7B="${AER_MODEL_PATH_7B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_PATH_14B="${AER_MODEL_PATH_14B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-14B-Instruct}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-$AER_MODEL_PATH_7B}"
export AER_DEMO_ORDER_COUNT="${AER_DEMO_ORDER_COUNT:-1200}"
export AER_MAX_STEPS="${AER_MAX_STEPS:-3}"
export AER_CASE_ID="${AER_CASE_ID:-AER-001}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-384}"
source scripts/env.sh

mkdir -p logs runtime artifacts
python -m aer_loop.cli model-smoke --orders "$AER_DEMO_ORDER_COUNT" --case-id "$AER_CASE_ID" --max-steps "$AER_MAX_STEPS" | tee "logs/model_quick_smoke_${AER_RUN_ID}.json"
python -m aer_loop.cli summary | tee "logs/model_quick_summary_${AER_RUN_ID}.json"
