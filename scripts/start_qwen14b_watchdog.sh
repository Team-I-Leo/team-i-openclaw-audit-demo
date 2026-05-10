#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
source scripts/env.sh

python scripts/download_models.py --model 14b --resume
