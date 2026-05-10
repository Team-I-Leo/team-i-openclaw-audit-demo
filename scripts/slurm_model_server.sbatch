#!/usr/bin/env bash
#SBATCH --job-name=aer-qwen7b
#SBATCH --partition=i64m1tga800u
#SBATCH --gres=gpu:a800:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=08:00:00
#SBATCH --output=logs/model_server_%j.out
#SBATCH --error=logs/model_server_%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
export AER_MODEL_PATH_7B="${AER_MODEL_PATH_7B:-$PWD/models/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_PATH_14B="${AER_MODEL_PATH_14B:-$PWD/models/Qwen2.5-Coder-14B-Instruct}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-$AER_MODEL_PATH_7B}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_MODEL_MAP="${AER_MODEL_MAP:-{\"qwen2.5-coder-7b-instruct\":\"$AER_MODEL_PATH_7B\",\"qwen2.5-coder-14b-instruct\":\"$AER_MODEL_PATH_14B\"}}"
export AER_MODEL_PORT="${AER_MODEL_PORT:-18088}"
exec bash scripts/serve_model.sh
