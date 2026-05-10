#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/env.sh

PLUGIN_DIR="$PWD/openclaw/plugins/aer_audit_tools"
if command -v npm >/dev/null 2>&1; then
  (cd "$PLUGIN_DIR" && npm install --no-audit --no-fund)
fi
openclaw plugins install "$PLUGIN_DIR"
