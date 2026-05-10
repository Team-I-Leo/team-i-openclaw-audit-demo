#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export AER_PROJECT_ROOT="$(pwd)"
source scripts/env.sh

export OPENCLAW_CONFIG_PATH="$AER_PROJECT_ROOT/openclaw/project_openclaw.json5"
export OPENCLAW_STATE_DIR="$AER_PROJECT_ROOT/runtime/openclaw-state"
mkdir -p "$OPENCLAW_STATE_DIR" logs runtime

openclaw gateway run --bind loopback --port "${AER_OPENCLAW_PORT:-18790}" --allow-unconfigured
