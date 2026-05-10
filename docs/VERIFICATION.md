# Team-I OpenCLAW Verification

Last verified on HPC2: 2026-05-10.

## Deterministic regression

Command:

```bash
cd /hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510
source scripts/env.sh
AER_MODEL_BACKEND=fallback python -m aer_loop.cli run --orders 4000 --max-steps 12 > logs/full_demo_fallback_run.json
python -m aer_loop.cli summary
```

Observed result:

- Cases: 3 (`AER-001` / `EC-SKIM-001`, `AER-002` / `EC-FAKE-002`, `AER-003` / `EC-ARBI-003`)
- Evidence rows: 27
- Trajectory rows: 71
- Case-thread action rows: 25
- Evidence Passports: 3
- Candidate patterns: 3

The fallback run is only a structural regression test. It is not the final intelligent-agent run.

## OpenCLAW tool invocation

Project gateway:

```text
API:      http://127.0.0.1:18083
OpenCLAW: http://127.0.0.1:18896
```

Validated through `/tools/invoke` with `aer_query_subsidy_ledger` against `AER-003`:

```json
{
  "ok": true,
  "action": "query_subsidy_ledger",
  "case_id": "AER-003",
  "metrics": {
    "subsidy_count": 72,
    "subsidy_total": 2997.75,
    "avg_subsidy": 41.635,
    "repeated_eligibility_keys": 15
  },
  "evidence_ids": ["EVD-AER-003-SUB-001"]
}
```

The call returned a normal OpenCLAW tool result and reached the Python governed action registry.

## Model-backed validation

The 0.5B checkpoint is no longer treated as a valid audit-agent model. It is smoke-only and should not be used in final demo claims.

Model-backed full validation:

```bash
sbatch scripts/slurm_model_full_debug.sbatch
```

Latest successful job:

```text
9728967 aer-full-debug
partition/node: debug / gpu3-9
state: COMPLETED
elapsed: 00:09:01
```

Observed result:

- Cases: 3 (`AER-001`, `AER-002`, `AER-003`)
- Evidence rows: 28
- Trajectory rows: 75
- Case-thread action rows: 24
- Evidence Passports: 3
- Model invocations: 75 local-model calls, `used_fallback=0` for every agent call
- Active evidence loop: 8 action steps per case before passport/human-review closeout

Role model mapping in the validated run:

- `risk_signal_agent`, `assertion_agent`, `case_router_agent`, `router_agent`, `investigation_agent`: `/hpc2hdd/home/hqi881/SWE-SQL/model/Qwen2.5-Coder-7B-Instruct`
- `pattern_matcher_agent`, `passport_agent`, `pattern_learning_agent`: `/hpc2hdd/home/hqi881/projects/deloitte-aer-loop-openclaw-20260510/models/Qwen2.5-Coder-14B-Instruct`

OpenAI-compatible model service validation:

```bash
sbatch scripts/slurm_openai_model_full_debug.sbatch
```

Latest successful job:

```text
9729073 aer-openai-full
partition/node: debug / gpu3-9
state: COMPLETED
elapsed: 00:08:04
allocation: 1 x A40, 8 CPU, 56G memory
```

Observed result:

- Cases: 3 (`AER-001`, `AER-002`, `AER-003`)
- Evidence rows: 28
- Trajectory rows: 75
- Case-thread action rows: 24
- Evidence Passports: 3
- Model invocations: 75 OpenAI-compatible HTTP calls, `used_fallback=0` for every agent call
- 7B role agents: `risk_signal_agent`, `assertion_agent`, `case_router_agent`, `router_agent`, `investigation_agent`
- 14B role agents: `pattern_matcher_agent`, `passport_agent`, `pattern_learning_agent`

Model service scripts:

- `scripts/serve_model.sh`
- `scripts/slurm_model_server.sbatch`
- `scripts/slurm_openai_model_full_debug.sbatch`
- `backend/aer_loop/model_server.py`

The model server now exposes `/health`, `/v1/models`, `/v1/chat/completions`, and `/v1/completions`. It supports role model IDs for `qwen2.5-coder-7b-instruct` and `qwen2.5-coder-14b-instruct`, and the OpenAI backend uses direct HTTP to avoid SDK dependency drift on HPC2.

Current 14B status:

- Watchdog download finished successfully.
- Target path: `models/Qwen2.5-Coder-14B-Instruct`.
- All six numbered shards are present and the runtime validated the 14B role agents in job `9728967`.

## Pattern Learning writeback

Validated against `runtime/aer_loop_model_smoke_9729073_openai_full_debug.sqlite`.

The product loop now supports:

- Candidate generation by `pattern_learning_agent`.
- Human review through `POST /api/patterns/candidates/{candidate_id}/review`.
- Approved candidate promotion into `risk_pattern`.
- Learned action priors in `policy_action_weight`.
- Historical reuse through `case_memory`.
- Router consumption of learned policy via `learned_policy_delta`.

Validation result:

```json
{
  "review_risk_pattern_id": "LEARNED-EC-ARBI-003",
  "original_arbi_status": "active",
  "learned_pattern_written": true,
  "policy_weight_rows": 16,
  "case_memory_ids": [
    "MEM-EC-ARBI-003-EC-ARBI-003",
    "MEM-EC-ARBI-003-LEARNED-EC-ARBI-003"
  ],
  "route_uses_learned_policy": true
}
```

Candidate IDs are namespace-guarded. If a model proposes an ID that collides with an existing production pattern such as `EC-ARBI-003`, the promoted learned pattern is written as `LEARNED-EC-ARBI-003` and the original `EC-ARBI-003` remains `active`.
