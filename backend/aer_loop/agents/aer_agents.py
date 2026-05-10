from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from ..config import settings
from ..db import jdump, jload
from ..llm_client import LLMClient, LLMResult
from ..policy import evidence_coverage, rank_actions
from ..schemas import ActionName, AgentDecision, Passport, ToolObservation


JSON_ONLY_SYSTEM = (
    "You are an audit AI agent in an OpenCLAW-style active evidence retrieval loop. "
    "Return exactly one valid JSON object only: no markdown fences, no prose, no comments. "
    "Numeric fields must be concrete numbers, never formulas or arithmetic expressions. "
    "Do not write SQL. You may only choose governed actions. "
    "Use concise audit reasoning grounded in the provided state and observations."
)


class ModelBackedAgent:
    agent_id = "base"
    role_model_attr = "openai_model"

    def __init__(self, con, llm: LLMClient | None = None):
        self.con = con
        role_model = getattr(settings, self.role_model_attr, settings.openai_model)
        self.llm = llm or LLMClient(model=role_model, role=self.agent_id)

    def _call_json(self, user: str, fallback: dict[str, Any], system: str = JSON_ONLY_SYSTEM) -> LLMResult:
        result = self.llm.generate_json(system=system, user=user, fallback=fallback)
        self.con.execute(
            """
            INSERT INTO model_invocation
            (agent_id, role, backend, model, used_fallback, prompt_chars, response_chars, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                self.agent_id,
                getattr(self.llm, "role", self.agent_id),
                result.backend,
                result.model,
                1 if result.used_fallback else 0,
                len(system) + len(user),
                len(result.text),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        return result

    def _case(self, case_id: str) -> dict[str, Any]:
        row = self.con.execute("SELECT * FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise KeyError(case_id)
        data = dict(row)
        data["primary_entities"] = jload(data["primary_entities"], {})
        data["scores"] = jload(data["scores"], {})
        data["signal_strength"] = jload(data.get("signal_strength"), {})
        data["evidence_requirements"] = jload(data.get("evidence_requirements"), {})
        data["next_actions"] = jload(data["next_actions"], [])
        return data

    def _recent_thread(self, case_id: str, limit: int = 8) -> list[dict[str, Any]]:
        rows = self.con.execute(
            """
            SELECT * FROM case_thread
            WHERE case_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (case_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def _evidence(self, case_id: str) -> list[dict[str, Any]]:
        rows = self.con.execute("SELECT * FROM evidence WHERE case_id=? ORDER BY evidence_id", (case_id,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["lineage"] = jload(item["lineage"], {})
            out.append(item)
        return out

    def record_trajectory(
        self,
        case_id: str,
        state: dict[str, Any],
        decision: dict[str, Any],
        observation: dict[str, Any] | None,
        reward: dict[str, Any] | None = None,
    ) -> None:
        self.con.execute(
            """
            INSERT INTO trajectory
            (case_id, agent_id, state_json, decision_json, observation_json, reward_json, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                case_id,
                self.agent_id,
                jdump(state),
                jdump(decision),
                jdump(observation or {}),
                jdump(reward or {}),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )

    def _normalize_decision_payload(self, parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        if "AgentDecision" in parsed and isinstance(parsed["AgentDecision"], dict):
            parsed = parsed["AgentDecision"]
        if "decision" in parsed and isinstance(parsed["decision"], dict):
            parsed = parsed["decision"]
        normalized = {**fallback, **parsed}
        if "action_name" in normalized and "action" not in normalized:
            normalized["action"] = normalized["action_name"]
        if "reason" in normalized and "reasoning" not in normalized:
            normalized["reasoning"] = normalized["reason"]
        if not isinstance(normalized.get("params"), dict):
            normalized["params"] = fallback.get("params", {})
        return normalized

    def _as_list(self, value: Any, fallback: list[Any]) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            return [value]
        return fallback


class RiskSignalAgent(ModelBackedAgent):
    agent_id = "risk_signal_agent"
    role_model_attr = "assertion_model"

    def assess_case(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        fallback = {
            "risk_signal_summary": case.get("signal_strength", {}),
            "weak_signals": [k for k, v in case.get("signal_strength", {}).items() if v == "weak"],
            "medium_signals": [k for k, v in case.get("signal_strength", {}).items() if v == "medium"],
            "strong_signals": [k for k, v in case.get("signal_strength", {}).items() if v == "strong"],
            "recommended_route": "full_investigation" if case["risk_score"] >= 0.72 else "light_investigation",
        }
        result = self._call_json(
            "Summarize weak/medium/strong risk signals for routing. "
            "risk_signal_summary must be under 30 words. "
            "weak_signals, medium_signals, and strong_signals must be arrays of signal keys only, not objects and not explanations. "
            "recommended_route must be one of: full_investigation, light_investigation.\n"
            "Return JSON keys: risk_signal_summary, weak_signals, medium_signals, strong_signals, recommended_route.\n"
            f"case={json.dumps(case, ensure_ascii=False)}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        self.record_trajectory(case_id, {"case": case}, {**parsed, "_llm": result.__dict__}, None)
        return parsed


class PatternMatcherAgent(ModelBackedAgent):
    agent_id = "pattern_matcher_agent"
    role_model_attr = "pattern_model"

    def match_pattern(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        rows = self.con.execute("SELECT * FROM case_memory WHERE pattern_id=?", (case["pattern_id"],)).fetchall()
        memory = [dict(r) for r in rows]
        for item in memory:
            item["signals"] = jload(item.get("signals"), [])
            item["counter_checks"] = jload(item.get("counter_checks"), [])
        fallback = {
            "matched_pattern": case["pattern_id"],
            "match_confidence": min(0.95, case["risk_score"]),
            "memory_hits": [m.get("memory_id") for m in memory],
            "route_hint": "full_investigation",
        }
        result = self._call_json(
            "Match the case to the structural risk pattern library and historical case memory. Return JSON keys: matched_pattern, match_confidence, memory_hits, route_hint.\n"
            f"case={json.dumps(case, ensure_ascii=False)}\n"
            f"memory={json.dumps(memory, ensure_ascii=False)}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        self.record_trajectory(case_id, {"case": case, "memory": memory}, {**parsed, "_llm": result.__dict__}, None)
        return parsed


class CaseRouterAgent(ModelBackedAgent):
    agent_id = "case_router_agent"
    role_model_attr = "router_model"

    def choose_depth(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        coverage = evidence_coverage(self.con, case_id)
        fallback = {
            "route": "full_investigation" if case["risk_score"] >= 0.72 else "light_investigation",
            "max_steps": 10 if case["risk_score"] >= 0.72 else 5,
            "must_collect": list(coverage.required.keys()),
            "human_gate": "required",
        }
        result = self._call_json(
            "Choose investigation depth and mandatory evidence dimensions. Return JSON keys: route, max_steps, must_collect, human_gate.\n"
            f"case={json.dumps(case, ensure_ascii=False)}\n"
            f"coverage={coverage}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        self.record_trajectory(case_id, {"case": case}, {**parsed, "_llm": result.__dict__}, None)
        return parsed


class AssertionAgent(ModelBackedAgent):
    agent_id = "assertion_agent"
    role_model_attr = "assertion_model"

    def build_assertion(self, case_id: str) -> dict[str, Any]:
        case = self._case(case_id)
        fallback = {
            "risk_assertion": case["assertion"],
            "hypothesis": "coordinated_shared_infrastructure_subsidy_skimming",
            "required_evidence": list(case.get("evidence_requirements", {}).keys()),
            "confidence": case["risk_score"],
        }
        result = self._call_json(
            "Create a short verifiable risk assertion for this case. "
            "Keep risk_assertion under 45 words and hypothesis under 20 words. "
            "required_evidence must be an array of dimension keys copied from case.evidence_requirements, not objects and not explanations.\n"
            f"Case JSON:\n{json.dumps(case, ensure_ascii=False)}\n"
            "Required JSON keys: risk_assertion, hypothesis, required_evidence, confidence.",
            fallback,
        )
        parsed = self._normalize_decision_payload(result.parsed_json or fallback, fallback)
        assertion = str(parsed.get("risk_assertion", fallback["risk_assertion"]))
        self.con.execute("UPDATE risk_case SET assertion=? WHERE case_id=?", (assertion, case_id))
        self.record_trajectory(case_id, {"case": case}, {**parsed, "_llm": result.__dict__}, None)
        return parsed


class RouterAgent(ModelBackedAgent):
    agent_id = "router_agent"
    role_model_attr = "router_model"

    def route(self, case_id: str, available_actions: list[str], executed: set[str] | None = None) -> AgentDecision:
        case = self._case(case_id)
        evidence = self._evidence(case_id)
        action_ranking = rank_actions(self.con, case_id, available_actions, executed=executed)
        top = action_ranking[0] if action_ranking else {"action": ActionName.emit_passport.value, "expected_evidence_gain": 0.0, "expected_cost": 0.0, "governance_risk": 0.0, "action_utility": 0.0}
        fallback = {
            "action": top["action"],
            "reasoning": "Choose the next governed evidence action that closes the largest current evidence gap.",
            "params": {},
            "expected_evidence_gain": top.get("expected_evidence_gain", 0.72),
            "expected_cost": top.get("expected_cost", 0.0),
            "governance_risk": top.get("governance_risk", 0.0),
            "action_utility": top.get("action_utility", 0.0),
            "stop_after_action": False,
        }
        result = self._call_json(
            "Select exactly one next action from available_actions for active audit evidence retrieval.\n"
            "Use the action_ranking utility table as a policy prior, but explain the audit reason.\n"
            "Return JSON keys: action, reasoning, params, expected_evidence_gain, expected_cost, governance_risk, action_utility, stop_after_action.\n"
            f"available_actions={available_actions}\n"
            f"action_ranking={json.dumps(action_ranking, ensure_ascii=False)}\n"
            f"case={json.dumps(case, ensure_ascii=False)}\n"
            f"evidence={json.dumps(evidence, ensure_ascii=False)}\n"
            f"recent_thread={json.dumps(self._recent_thread(case_id), ensure_ascii=False)}",
            fallback,
        )
        parsed = self._normalize_decision_payload(result.parsed_json or fallback, fallback)
        if parsed.get("action") not in available_actions:
            parsed["action"] = fallback["action"]
            parsed["reasoning"] = f"{parsed.get('reasoning','')} Invalid model action replaced by governed fallback."
        chosen = next((item for item in action_ranking if item["action"] == parsed.get("action")), top)
        for key in ["expected_evidence_gain", "expected_cost", "governance_risk", "action_utility"]:
            parsed[key] = chosen.get(key, fallback.get(key, 0.0))
        try:
            decision = AgentDecision.model_validate(parsed)
        except ValidationError:
            decision = AgentDecision.model_validate(fallback)
        self.record_trajectory(case_id, {"available_actions": available_actions, "action_ranking": action_ranking, "case": case, "evidence": evidence}, {**decision.model_dump(), "_llm": result.__dict__}, None)
        return decision

    def _first_missing_action(self, evidence: list[dict[str, Any]], available_actions: list[str]) -> str:
        dims = {e["dimension"] for e in evidence}
        priority = [
            ("device_reuse", ActionName.expand_infra_graph.value),
            ("refund_abnormal", ActionName.query_refund_cluster.value),
            ("payment_cluster", ActionName.query_payment_cluster.value),
            ("logistics_authenticity", ActionName.query_logistics_trace.value),
            ("promo_cohort_outlier", ActionName.compare_promo_cohort.value),
            ("counter_evidence_gap", ActionName.seek_counter_evidence.value),
        ]
        for dim, action in priority:
            if dim not in dims and action in available_actions:
                return action
        return ActionName.emit_passport.value if ActionName.emit_passport.value in available_actions else available_actions[0]


class InvestigationAgent(ModelBackedAgent):
    agent_id = "investigation_agent"
    role_model_attr = "investigation_model"

    def reflect_observation(self, case_id: str, decision: AgentDecision, observation: ToolObservation) -> dict[str, Any]:
        case = self._case(case_id)
        compact_observation = observation.model_dump()
        if "graph_delta" in compact_observation:
            compact_observation["graph_delta"] = {
                "metrics": compact_observation.get("graph_delta", {}).get("metrics", {}),
                "sample_nodes": compact_observation.get("graph_delta", {}).get("nodes", [])[:8],
                "sample_edges": compact_observation.get("graph_delta", {}).get("edges", [])[:8],
            }
        fallback = {
            "observation_assessment": observation.summary,
            "evidence_gap_update": observation.next_recommended_actions,
            "process_reward": {
                "evidence_gain": min(1.0, len(observation.support_evidence) * 0.18 + len(observation.counter_evidence) * 0.12),
                "counter_evidence_covered": bool(observation.counter_evidence),
                "unsupported_claim_risk": 0.18,
            },
            "continue_investigation": observation.action != ActionName.emit_passport,
        }
        result = self._call_json(
            "Assess the just executed audit action. Return JSON keys: observation_assessment, evidence_gap_update, process_reward, continue_investigation.\n"
            f"case={json.dumps(case, ensure_ascii=False)}\n"
            f"decision={decision.model_dump_json()}\n"
            f"observation={json.dumps(compact_observation, ensure_ascii=False)}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        self.record_trajectory(case_id, {"case": case}, {"decision": decision.model_dump(), "assessment": parsed, "_llm": result.__dict__}, observation.model_dump(), parsed.get("process_reward", {}))
        return parsed


class CounterEvidenceAgent(ModelBackedAgent):
    agent_id = "counter_evidence_agent"
    role_model_attr = "counter_model"

    def should_seek_counter(self, case_id: str) -> AgentDecision:
        evidence = self._evidence(case_id)
        fallback = {
            "action": ActionName.seek_counter_evidence.value,
            "reasoning": "Support evidence exists but counter-evidence coverage is still incomplete.",
            "params": {"counter_checks": ["CTR-001", "CTR-002", "CTR-003", "CTR-004", "CTR-005"]},
            "expected_evidence_gain": 0.64,
            "stop_after_action": False,
        }
        result = self._call_json(
            "Decide whether the case needs counter-evidence search. Return the same AgentDecision JSON schema.\n"
            f"evidence={json.dumps(evidence, ensure_ascii=False)}",
            fallback,
        )
        parsed = self._normalize_decision_payload(result.parsed_json or fallback, fallback)
        parsed["action"] = ActionName.seek_counter_evidence.value
        try:
            decision = AgentDecision.model_validate(parsed)
        except ValidationError:
            decision = AgentDecision.model_validate(fallback)
        self.record_trajectory(case_id, {"evidence": evidence}, {**decision.model_dump(), "_llm": result.__dict__}, None)
        return decision


class PassportAgent(ModelBackedAgent):
    agent_id = "passport_agent"
    role_model_attr = "passport_model"

    def build_passport(self, case_id: str) -> Passport:
        case = self._case(case_id)
        evidence = self._evidence(case_id)
        support = [e for e in evidence if e["kind"] == "support"]
        counter = [e for e in evidence if e["kind"] != "support"]
        cov = evidence_coverage(self.con, case_id)
        coverage = {
            dim: "covered" if cov.covered.get(dim, 0.0) >= 0.45 else "missing"
            for dim in cov.required
        }
        coverage["_sufficiency_score"] = str(cov.sufficiency_score)
        fallback = {
            "model_narrative": "The case has multi-source support evidence and limited counter-evidence. Human review is required before disposition.",
            "remaining_uncertainty": ["Payment account ownership still requires review.", "Warehouse batch shipping is only partially ruled out."],
            "recommended_action": ["Submit to human review", "Do not freeze funds automatically", "Request payment ownership verification"],
        }
        result = self._call_json(
            "Write concise audit-passport narrative JSON. Return keys: model_narrative, remaining_uncertainty, recommended_action.\n"
            f"case={json.dumps(case, ensure_ascii=False)}\n"
            f"evidence={json.dumps(evidence, ensure_ascii=False)}\n"
            f"coverage={json.dumps(coverage, ensure_ascii=False)}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        passport = Passport(
            case_header={
                "case_id": case_id,
                "site": "US",
                "promo_window": "Black Friday 2025",
                "risk_pattern": case["pattern_id"],
                "risk_level": case["risk_level"],
                "status": "human_review_required",
            },
            risk_assertion=case["assertion"],
            support_evidence=support,
            counter_evidence=counter,
            evidence_coverage=coverage,
            remaining_uncertainty=self._as_list(parsed.get("remaining_uncertainty"), fallback["remaining_uncertainty"]),
            recommended_action=self._as_list(parsed.get("recommended_action"), fallback["recommended_action"]),
            human_gate={"required": True, "gate_id": "GATE-02", "reason": "Evidence quality and disposition require auditor review.", "sufficiency_score": cov.sufficiency_score, "counter_score": cov.counter_score},
            versions={"pattern_version": f"{case['pattern_id']}:demo", "policy_version": "aer_policy_v1", "tool_version": "openclaw_toolset_v1"},
            model_narrative=str(parsed.get("model_narrative", fallback["model_narrative"])),
        )
        self.con.execute(
            "INSERT OR REPLACE INTO passport VALUES (?,?,?)",
            (case_id, passport.model_dump_json(), datetime.utcnow().isoformat(timespec="seconds")),
        )
        self.con.execute("UPDATE risk_case SET status=? WHERE case_id=?", ("human_review_required", case_id))
        self.record_trajectory(case_id, {"case": case, "evidence": evidence}, {**parsed, "_llm": result.__dict__}, passport.model_dump())
        return passport


class PatternLearningAgent(ModelBackedAgent):
    agent_id = "pattern_learning_agent"
    role_model_attr = "pattern_model"

    def propose_candidate(self, case_ids: list[str]) -> dict[str, Any]:
        cases = [self._case(case_id) for case_id in case_ids]
        evidence = {case_id: self._evidence(case_id) for case_id in case_ids}
        candidate_suffix = "-".join(case_ids) if len(case_ids) <= 3 else f"{len(case_ids)}-cases"
        fallback = {
            "candidate_pattern_id": f"CAND-2026-{candidate_suffix}",
            "name": f"AER learned pattern candidate from {candidate_suffix}",
            "supporting_cases": case_ids,
            "common_signals": ["device_reuse", "refund_under_24h", "payment_cluster", "promo_cohort_outlier"],
            "required_counter_checks": ["family_shared_device", "promo_natural_traffic", "warehouse_batch_shipping"],
            "status": "under_review",
        }
        result = self._call_json(
            "Summarize a candidate risk pattern for human approval. Return JSON keys: candidate_pattern_id, name, supporting_cases, common_signals, required_counter_checks, status.\n"
            f"cases={json.dumps(cases, ensure_ascii=False)}\n"
            f"evidence={json.dumps(evidence, ensure_ascii=False)}",
            fallback,
        )
        parsed = result.parsed_json or fallback
        candidate_id = str(parsed.get("candidate_pattern_id", fallback["candidate_pattern_id"]))
        if not candidate_id.startswith(("CAND-", "LEARNED-")):
            candidate_id = fallback["candidate_pattern_id"]
        parsed["candidate_pattern_id"] = candidate_id
        self.con.execute(
            "INSERT OR REPLACE INTO candidate_pattern VALUES (?,?,?,?,?,?,?)",
            (
                candidate_id,
                parsed.get("name", fallback["name"]),
                jdump(parsed.get("supporting_cases", case_ids)),
                jdump(parsed.get("common_signals", fallback["common_signals"])),
                jdump(parsed.get("required_counter_checks", fallback["required_counter_checks"])),
                parsed.get("status", "under_review"),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        self.record_trajectory("PATTERN-LEARNING", {"case_ids": case_ids}, {**parsed, "_llm": result.__dict__}, None)
        return parsed
