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
cd /hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510
export AER_MODEL_PATH="${AER_MODEL_PATH:-/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_MODEL_MAP="${AER_MODEL_MAP:-{\"qwen2.5-coder-7b-instruct\":\"/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct\",\"qwen2.5-coder-14b-instruct\":\"/hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510/models/Qwen2.5-Coder-14B-Instruct\"}}"
export AER_MODEL_PORT="${AER_MODEL_PORT:-18088}"
export AER_CONDA_ENV="${AER_CONDA_ENV:-toplora_py311}"
exec bash scripts/serve_model.sh
