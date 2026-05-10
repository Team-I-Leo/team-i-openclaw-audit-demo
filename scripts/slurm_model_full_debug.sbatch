#!/usr/bin/env bash
#SBATCH --job-name=aer-full-debug
#SBATCH --partition=debug
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:25:00
#SBATCH --output=logs/slurm_model_full_debug_%j.out
#SBATCH --error=logs/slurm_model_full_debug_%j.err

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
export AER_RUN_ID="${SLURM_JOB_ID}_full_debug"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-local}"
export AER_MODEL_PATH_7B="${AER_MODEL_PATH_7B:-$PWD/models/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_PATH_14B="${AER_MODEL_PATH_14B:-$PWD/models/Qwen2.5-Coder-14B-Instruct}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-$AER_MODEL_PATH_7B}"
export AER_DEMO_ORDER_COUNT="${AER_DEMO_ORDER_COUNT:-3000}"
export AER_MAX_STEPS="${AER_MAX_STEPS:-8}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-384}"
scripts/run_model_smoke.sh
