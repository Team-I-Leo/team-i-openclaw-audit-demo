#!/usr/bin/env bash
set -euo pipefail

export AER_PROJECT_ROOT="${AER_PROJECT_ROOT:-/hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510}"
export PYTHONPATH="$AER_PROJECT_ROOT/backend:${PYTHONPATH:-}"
export PYTHONNOUSERSITE=1
export AER_MODEL_PATH="${AER_MODEL_PATH:-/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-fallback}"
export AER_OPENAI_BASE_URL="${AER_OPENAI_BASE_URL:-http://127.0.0.1:18088/v1}"
export AER_OPENAI_API_KEY="${AER_OPENAI_API_KEY:-EMPTY}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_ASSERTION_MODEL="${AER_ASSERTION_MODEL:-$AER_OPENAI_MODEL}"
export AER_ROUTER_MODEL="${AER_ROUTER_MODEL:-$AER_OPENAI_MODEL}"
export AER_INVESTIGATION_MODEL="${AER_INVESTIGATION_MODEL:-$AER_OPENAI_MODEL}"
export AER_COUNTER_MODEL="${AER_COUNTER_MODEL:-$AER_OPENAI_MODEL}"
export AER_PASSPORT_MODEL="${AER_PASSPORT_MODEL:-qwen2.5-coder-14b-instruct}"
export AER_PATTERN_MODEL="${AER_PATTERN_MODEL:-qwen2.5-coder-14b-instruct}"

if [ -f /hpc2ssd/softwares/anaconda3/etc/profile.d/conda.sh ]; then
  source /hpc2ssd/softwares/anaconda3/etc/profile.d/conda.sh
elif [ -f /hpc2hdd/home/hqi881/.conda/etc/profile.d/conda.sh ]; then
  source /hpc2hdd/home/hqi881/.conda/etc/profile.d/conda.sh
fi

conda activate "${AER_CONDA_ENV:-openclaw}"
