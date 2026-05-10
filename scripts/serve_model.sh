#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
export AER_MODEL_PATH="${AER_MODEL_PATH:-/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-512}"
export AER_CONDA_ENV="${AER_CONDA_ENV:-toplora_py311}"
source scripts/env.sh

mkdir -p logs runtime artifacts
# The serving environment already has torch/transformers in conda, while uvicorn
# is installed in the user's site-packages on HPC2.
unset PYTHONNOUSERSITE
exec python -m uvicorn aer_loop.model_server:app --host 127.0.0.1 --port "${AER_MODEL_PORT:-18088}"
