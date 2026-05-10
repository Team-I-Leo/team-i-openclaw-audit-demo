#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs
sbatch scripts/slurm_gpu_model_smoke.sbatch

