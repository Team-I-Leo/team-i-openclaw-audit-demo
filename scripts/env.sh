#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AER_PROJECT_ROOT="${AER_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

if [[ -f "$AER_PROJECT_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$AER_PROJECT_ROOT/.env"
  set +a
fi

export PYTHONPATH="$AER_PROJECT_ROOT/backend:${PYTHONPATH:-}"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-fallback}"
export AER_MODEL_PATH_7B="${AER_MODEL_PATH_7B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-7B-Instruct}"
export AER_MODEL_PATH_14B="${AER_MODEL_PATH_14B:-$AER_PROJECT_ROOT/models/Qwen2.5-Coder-14B-Instruct}"
export AER_MODEL_PATH="${AER_MODEL_PATH:-$AER_MODEL_PATH_7B}"
export AER_OPENAI_BASE_URL="${AER_OPENAI_BASE_URL:-http://127.0.0.1:${AER_MODEL_PORT:-18088}/v1}"
export AER_OPENAI_API_KEY="${AER_OPENAI_API_KEY:-EMPTY}"
export AER_OPENAI_MODEL="${AER_OPENAI_MODEL:-qwen2.5-coder-7b-instruct}"
export AER_ASSERTION_MODEL="${AER_ASSERTION_MODEL:-$AER_OPENAI_MODEL}"
export AER_ROUTER_MODEL="${AER_ROUTER_MODEL:-$AER_OPENAI_MODEL}"
export AER_INVESTIGATION_MODEL="${AER_INVESTIGATION_MODEL:-$AER_OPENAI_MODEL}"
export AER_COUNTER_MODEL="${AER_COUNTER_MODEL:-$AER_OPENAI_MODEL}"
export AER_PASSPORT_MODEL="${AER_PASSPORT_MODEL:-qwen2.5-coder-14b-instruct}"
export AER_PATTERN_MODEL="${AER_PATTERN_MODEL:-qwen2.5-coder-14b-instruct}"

if [[ -n "${AER_CONDA_ENV:-}" ]]; then
  if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate "$AER_CONDA_ENV"
  elif [[ -f "${CONDA_PREFIX:-}/etc/profile.d/conda.sh" ]]; then
    # shellcheck disable=SC1091
    source "${CONDA_PREFIX}/etc/profile.d/conda.sh"
    conda activate "$AER_CONDA_ENV"
  else
    echo "AER_CONDA_ENV=$AER_CONDA_ENV was set, but conda was not found." >&2
    exit 1
  fi
fi
