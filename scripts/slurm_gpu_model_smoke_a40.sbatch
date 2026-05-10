#!/usr/bin/env bash
#SBATCH --job-name=aer-qwen7b-a40
#SBATCH --partition=i64m1tga40u8ka
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=00:45:00
#SBATCH --output=logs/slurm_model_smoke_a40_%j.out
#SBATCH --error=logs/slurm_model_smoke_a40_%j.err

set -euo pipefail
cd /hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510
export AER_RUN_ID="${SLURM_JOB_ID}_a40"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-local}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct}"
export AER_CONDA_ENV="${AER_CONDA_ENV:-toplora_py311}"
export AER_DEMO_ORDER_COUNT="${AER_DEMO_ORDER_COUNT:-2000}"
export AER_MAX_STEPS="${AER_MAX_STEPS:-4}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-160}"
scripts/run_model_smoke.sh
