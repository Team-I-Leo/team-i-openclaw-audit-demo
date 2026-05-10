#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
export AER_MODEL_PATH_7B="${AER_MODEL_PATH_7B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_PATH_14B="${AER_MODEL_PATH_14B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-14B-Instruct}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-$AER_MODEL_PATH_7B}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-512}"
source scripts/env.sh

mkdir -p logs runtime artifacts
exec python -m uvicorn aer_loop.model_server:app --host 127.0.0.1 --port "${AER_MODEL_PORT:-18088}"
