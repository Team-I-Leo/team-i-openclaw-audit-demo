#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
export AER_MODEL_BACKEND="${AER_MODEL_BACKEND:-fallback}"
source scripts/env.sh

mkdir -p logs runtime artifacts
exec uvicorn app:app --app-dir backend --host 127.0.0.1 --port "${AER_API_PORT:-18081}"
