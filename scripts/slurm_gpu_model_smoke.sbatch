#!/usr/bin/env bash
#SBATCH --job-name=aer-openclaw-model-smoke
#SBATCH --partition=i64m1tga800u
#SBATCH --gres=gpu:a800:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=80G
#SBATCH --time=01:00:00
#SBATCH --output=logs/slurm_model_smoke_%j.out
#SBATCH --error=logs/slurm_model_smoke_%j.err

set -euo pipefail
cd /hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-local}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct}"
export AER_CONDA_ENV="${AER_CONDA_ENV:-toplora_py311}"
export AER_DEMO_ORDER_COUNT="${AER_DEMO_ORDER_COUNT:-3000}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-192}"
scripts/run_model_smoke.sh
