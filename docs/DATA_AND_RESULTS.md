# Data and Results

This repository contains the demo data and compact validation outputs needed to replay the Team-I audit workflow without shipping model weights.

## Included

- `data/patterns/*.yaml`: seed risk patterns.
- `runtime/aer_loop_model_smoke_9728967_full_debug.sqlite`: final local-model validated database.
- `runtime/pattern_learning_writeback_test.sqlite`: human-review writeback validation database.
- `runtime/aer_loop_model_quick_*.sqlite`: quick model smoke databases.
- `logs/model_summary_*.json`: compact validation summaries.
- `logs/model_smoke_run_*.json`: selected run outputs.
- `materials/route_calibration_materials.tar.gz`: original route-calibration materials as an archive.

## Excluded

- `models/`: model weights are too large for GitHub and should be downloaded or mounted separately.
- `runtime/aer_loop_model_smoke_9729073_openai_full_debug.sqlite`: excluded because the raw SQLite file exceeds GitHub's single-file limit after later service mutations. The validation summary remains in `logs/model_summary_9729073_openai_full_debug.json`.
- API process logs and PID files: local runtime noise, not needed for replay.

## Replaying the Main Result

```bash
export PYTHONPATH="$PWD/backend:${PYTHONPATH:-}"
export AER_DB_PATH="$PWD/runtime/aer_loop_model_smoke_9728967_full_debug.sqlite"
python -m aer_loop.cli summary
```

