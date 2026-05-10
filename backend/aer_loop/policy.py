from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .db import jload
from .schemas import ActionName


ACTION_DIMENSIONS = {
    ActionName.expand_infra_graph.value: ["device_reuse", "ip_cluster"],
    ActionName.query_refund_cluster.value: ["refund_abnormal"],
    ActionName.query_logistics_trace.value: ["logistics_authenticity"],
    ActionName.query_payment_cluster.value: ["payment_cluster"],
    ActionName.compare_promo_cohort.value: ["promo_cohort_outlier"],
    ActionName.query_subsidy_ledger.value: ["subsidy_abuse"],
    ActionName.analyze_behavior_sequence.value: ["review_similarity", "behavior_automation"],
    ActionName.search_historical_cases.value: ["historical_pattern_match"],
    ActionName.seek_counter_evidence.value: ["counter_evidence"],
    ActionName.request_human_review.value: [],
    ActionName.emit_passport.value: [],
}

ACTION_COST = {
    ActionName.expand_infra_graph.value: 0.18,
    ActionName.query_refund_cluster.value: 0.15,
    ActionName.query_logistics_trace.value: 0.20,
    ActionName.query_payment_cluster.value: 0.18,
    ActionName.compare_promo_cohort.value: 0.16,
    ActionName.query_subsidy_ledger.value: 0.14,
    ActionName.analyze_behavior_sequence.value: 0.22,
    ActionName.search_historical_cases.value: 0.12,
    ActionName.seek_counter_evidence.value: 0.24,
    ActionName.request_human_review.value: 0.10,
    ActionName.emit_passport.value: 0.08,
}

GOVERNANCE_RISK = {
    ActionName.expand_infra_graph.value: 0.12,
    ActionName.query_refund_cluster.value: 0.14,
    ActionName.query_logistics_trace.value: 0.12,
    ActionName.query_payment_cluster.value: 0.18,
    ActionName.compare_promo_cohort.value: 0.08,
    ActionName.query_subsidy_ledger.value: 0.16,
    ActionName.analyze_behavior_sequence.value: 0.14,
    ActionName.search_historical_cases.value: 0.06,
    ActionName.seek_counter_evidence.value: 0.10,
    ActionName.request_human_review.value: 0.02,
    ActionName.emit_passport.value: 0.02,
}


@dataclass(frozen=True)
class EvidenceCoverage:
    required: dict[str, float]
    covered: dict[str, float]
    missing: dict[str, float]
    support_score: float
    counter_score: float
    sufficiency_score: float
    passport_ready: bool


def evidence_coverage(con, case_id: str) -> EvidenceCoverage:
    case = con.execute("SELECT evidence_requirements FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
    required = jload(case["evidence_requirements"], {}) if case else {}
    if not required:
        required = {"device_reuse": 0.16, "ip_cluster": 0.14, "payment_cluster": 0.14, "counter_evidence": 0.1}

    covered: dict[str, float] = {}
    counter_score = 0.0
    rows = con.execute("SELECT kind, dimension, confidence FROM evidence WHERE case_id=?", (case_id,)).fetchall()
    for row in rows:
        dim = row["dimension"]
        conf = float(row["confidence"])
        if row["kind"] == "support":
            covered[dim] = max(covered.get(dim, 0.0), conf)
        elif row["kind"] in {"counter", "uncertainty"}:
            counter_score = max(counter_score, conf)
            covered["counter_evidence"] = max(covered.get("counter_evidence", 0.0), min(1.0, conf))

    missing = {dim: weight for dim, weight in required.items() if covered.get(dim, 0.0) < 0.45}
    support_score = 0.0
    for dim, weight in required.items():
        if dim == "counter_evidence":
            continue
        support_score += min(1.0, covered.get(dim, 0.0)) * float(weight)
    max_support = sum(float(w) for d, w in required.items() if d != "counter_evidence") or 1.0
    normalized_support = support_score / max_support
    sufficiency = min(1.0, 0.82 * normalized_support + 0.18 * counter_score)
    passport_ready = sufficiency >= 0.78 and counter_score >= 0.45 and len(missing) == 0
    return EvidenceCoverage(required, covered, missing, round(normalized_support, 3), round(counter_score, 3), round(sufficiency, 3), passport_ready)


def rank_actions(con, case_id: str, available_actions: list[str], executed: set[str] | None = None) -> list[dict[str, Any]]:
    executed = executed or set()
    coverage = evidence_coverage(con, case_id)
    policy_weights = _learned_policy_weights(con, case_id)
    ranked: list[dict[str, Any]] = []
    for action in available_actions:
        if action in executed:
            continue
        dims = ACTION_DIMENSIONS.get(action, [])
        missing_gain = sum(float(coverage.required.get(dim, 0.0)) * (1.0 - coverage.covered.get(dim, 0.0)) for dim in dims)
        novelty = 0.16 if dims and any(dim in coverage.missing for dim in dims) else 0.03
        if action == ActionName.seek_counter_evidence.value and coverage.counter_score < 0.45:
            support_missing = [dim for dim in coverage.missing if dim != "counter_evidence"]
            novelty += 0.24 if not support_missing else -0.12
        if action == ActionName.emit_passport.value:
            novelty = 0.72 if coverage.passport_ready else -0.35
        if action == ActionName.request_human_review.value:
            novelty = 0.45 if coverage.passport_ready else 0.05
        cost = ACTION_COST.get(action, 0.2)
        gov = GOVERNANCE_RISK.get(action, 0.1)
        learned_weight_delta = max(-0.18, min(0.18, policy_weights.get(action, 0.0)))
        utility = max(-1.0, min(1.0, missing_gain + novelty + learned_weight_delta - 0.35 * cost - 0.25 * gov))
        ranked.append(
            {
                "action": action,
                "covers": dims,
                "expected_evidence_gain": round(max(0.0, min(1.0, missing_gain + novelty)), 3),
                "expected_cost": cost,
                "governance_risk": gov,
                "learned_policy_delta": round(learned_weight_delta, 3),
                "action_utility": round(utility, 3),
                "reason": _policy_reason(missing_gain, learned_weight_delta),
            }
        )
    ranked.sort(key=lambda item: item["action_utility"], reverse=True)
    return ranked


def _learned_policy_weights(con, case_id: str) -> dict[str, float]:
    case = con.execute("SELECT pattern_id FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
    if not case:
        return {}
    try:
        rows = con.execute(
            """
            SELECT action_name, SUM(weight_delta) delta
            FROM policy_action_weight
            WHERE pattern_id=?
            GROUP BY action_name
            """,
            (case["pattern_id"],),
        ).fetchall()
    except Exception:
        return {}
    return {row["action_name"]: float(row["delta"] or 0.0) for row in rows}


def _policy_reason(missing_gain: float, learned_weight_delta: float) -> str:
    if learned_weight_delta > 0 and missing_gain > 0:
        return "fills missing evidence dimensions and is reinforced by approved learned policy"
    if learned_weight_delta > 0:
        return "reinforced by approved learned policy"
    if missing_gain > 0:
        return "fills missing evidence dimensions"
    return "terminal or low-gap action"
