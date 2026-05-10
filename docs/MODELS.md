# Models

Model weights are intentionally not included in the GitHub repository.

## Validated Role Mapping

The final HPC2 validation used the following mapping:

| Role | Model |
| --- | --- |
| `risk_signal_agent` | Qwen2.5-Coder-7B-Instruct |
| `assertion_agent` | Qwen2.5-Coder-7B-Instruct |
| `case_router_agent` | Qwen2.5-Coder-7B-Instruct |
| `router_agent` | Qwen2.5-Coder-7B-Instruct |
| `investigation_agent` | Qwen2.5-Coder-7B-Instruct |
| `pattern_matcher_agent` | Qwen2.5-Coder-14B-Instruct |
| `passport_agent` | Qwen2.5-Coder-14B-Instruct |
| `pattern_learning_agent` | Qwen2.5-Coder-14B-Instruct |

## Environment Variables

```bash
export AER_MODEL_BACKEND=local
export AER_MODEL_PATH=/path/to/Qwen2.5-Coder-7B-Instruct
export AER_MODEL_14B_PATH=/path/to/Qwen2.5-Coder-14B-Instruct
```

For OpenAI-compatible local serving:

```bash
export AER_MODEL_BACKEND=openai
export AER_OPENAI_BASE_URL=http://127.0.0.1:18080/v1
```

The 0.5B checkpoint is not considered suitable for final audit-agent claims. It should only be used for connectivity smoke tests.

