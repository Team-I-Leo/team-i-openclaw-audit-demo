#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
source scripts/env.sh

mkdir -p logs runtime artifacts
python -m aer_loop.cli run --orders "${AER_DEMO_ORDER_COUNT:-12000}" --max-steps 8 | tee logs/smoke_run.json
python -m aer_loop.cli summary | tee logs/summary.json

