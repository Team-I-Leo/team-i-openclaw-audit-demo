#!/usr/bin/env bash
#SBATCH --job-name=aer-openai-full
#SBATCH --partition=debug
#SBATCH --gres=gpu:a40:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=56G
#SBATCH --time=00:29:00
#SBATCH --output=logs/slurm_openai_full_%j.out
#SBATCH --error=logs/slurm_openai_full_%j.err

set -euo pipefail
cd /hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510

export AER_CONDA_ENV="${AER_CONDA_ENV:-toplora_py311}"
export AER_MODEL_PORT="${AER_MODEL_PORT:-18088}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_MODEL_MAP="${AER_MODEL_MAP:-{\"qwen2.5-coder-7b-instruct\":\"/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct\",\"qwen2.5-coder-14b-instruct\":\"/hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510/models/Qwen2.5-Coder-14B-Instruct\"}}"
export AER_MAX_NEW_TOKENS="${AER_MAX_NEW_TOKENS:-384}"
source scripts/env.sh

mkdir -p logs runtime artifacts
scripts/serve_model.sh > "logs/model_server_${SLURM_JOB_ID}.out" 2> "logs/model_server_${SLURM_JOB_ID}.err" &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 90); do
  if python - <<PY
import urllib.request
urllib.request.urlopen("http://127.0.0.1:${AER_MODEL_PORT}/health", timeout=2).read()
PY
  then
    break
  fi
  sleep 5
done

python - <<PY
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:${AER_MODEL_PORT}/health", timeout=5).read().decode())
PY

export AER_RUN_ID="${SLURM_JOB_ID}_openai_full_debug"
export AER_MODEL_BACKEND="openai"
export AER_OPENAI_BASE_URL="http://127.0.0.1:${AER_MODEL_PORT}/v1"
export AER_OPENAI_API_KEY="${AER_OPENAI_API_KEY:-EMPTY}"
export AER_DEMO_ORDER_COUNT="${AER_DEMO_ORDER_COUNT:-3000}"
export AER_MAX_STEPS="${AER_MAX_STEPS:-8}"
export AER_ASSERTION_MODEL="${AER_ASSERTION_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_ROUTER_MODEL="${AER_ROUTER_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_INVESTIGATION_MODEL="${AER_INVESTIGATION_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_COUNTER_MODEL="${AER_COUNTER_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_PASSPORT_MODEL="${AER_PASSPORT_MODEL:-qwen2.5-coder-14b-instruct}"
export AER_PATTERN_MODEL="${AER_PATTERN_MODEL:-qwen2.5-coder-14b-instruct}"

scripts/run_model_smoke.sh
