# Team-I OpenCLAW Implementation Plan

This implementation targets the full demo route, not a minimal MVP:

1. Multi-source data fusion across ecommerce orders, payments, refunds, logistics, comments, gateway logs, device logs, subsidy ledger, logistics tracks, IEEE-CIS-style public features, and historical case memory.
2. Three business scenarios: `EC-SKIM-001`, `EC-FAKE-002`, and `EC-ARBI-003`.
3. Model-backed agents with governed fallback: RiskSignalAgent, PatternMatcherAgent, CaseRouterAgent, AssertionAgent, RouterAgent, InvestigationAgent, CounterEvidenceAgent, PassportAgent, and PatternLearningAgent.
4. Active evidence retrieval policy with action utility, expected evidence gain, cost, governance risk, support coverage, counter-evidence coverage, and passport readiness.
5. OpenCLAW project gateway plus `aer-audit-tools` plugin exposing governed audit actions through `/tools/invoke`.
6. Evidence Passport and Human Review gate.

## Model allocation

- Router / Investigation / Assertion / CounterEvidence: `qwen2.5-coder-7b-instruct`
- Passport / PatternLearning: `qwen2.5-coder-14b-instruct`
- Case-memory retrieval assets: Qwen3 Embedding 8B and Qwen3 Reranker 8B paths are configured for retrieval expansion.

The 0.5B checkpoint is not a valid audit-agent model for this demo.

## Remaining runtime dependency

The full model-backed run depends on GPU allocation on HPC2. The deterministic fallback run verifies system structure; Slurm GPU validation verifies LLM participation once resources are assigned.
