from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    support = "support"
    counter = "counter"
    uncertainty = "uncertainty"


class ActionName(str, Enum):
    expand_infra_graph = "expand_infra_graph"
    query_refund_cluster = "query_refund_cluster"
    query_logistics_trace = "query_logistics_trace"
    query_payment_cluster = "query_payment_cluster"
    compare_promo_cohort = "compare_promo_cohort"
    query_subsidy_ledger = "query_subsidy_ledger"
    analyze_behavior_sequence = "analyze_behavior_sequence"
    search_historical_cases = "search_historical_cases"
    seek_counter_evidence = "seek_counter_evidence"
    request_human_review = "request_human_review"
    emit_passport = "emit_passport"


class AgentDecision(BaseModel):
    action: ActionName
    reasoning: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    expected_evidence_gain: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_cost: float = Field(default=0.0, ge=0.0, le=1.0)
    governance_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    action_utility: float = Field(default=0.0, ge=-1.0, le=1.0)
    stop_after_action: bool = False


class EvidenceItem(BaseModel):
    evidence_id: str
    case_id: str
    kind: EvidenceKind
    dimension: str
    description: str
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    lineage: dict[str, Any] = Field(default_factory=dict)


class ToolObservation(BaseModel):
    action: ActionName
    case_id: str
    summary: str
    support_evidence: list[EvidenceItem] = Field(default_factory=list)
    counter_evidence: list[EvidenceItem] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    graph_delta: dict[str, Any] = Field(default_factory=dict)
    next_recommended_actions: list[ActionName] = Field(default_factory=list)
    source_lineage: list[dict[str, Any]] = Field(default_factory=list)


class AuditCase(BaseModel):
    case_id: str
    pattern_id: str
    pattern_name: str
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: float
    assertion: str
    status: str
    created_at: str
    primary_entities: dict[str, list[str]]
    scores: dict[str, float]
    signal_strength: dict[str, str] = Field(default_factory=dict)
    evidence_requirements: dict[str, float] = Field(default_factory=dict)
    next_actions: list[ActionName] = Field(default_factory=list)


class Passport(BaseModel):
    model_config = {"protected_namespaces": ()}

    case_header: dict[str, Any]
    risk_assertion: str
    support_evidence: list[dict[str, Any]]
    counter_evidence: list[dict[str, Any]]
    evidence_coverage: dict[str, str]
    remaining_uncertainty: list[str]
    recommended_action: list[str]
    human_gate: dict[str, Any]
    versions: dict[str, str]
    model_narrative: str
