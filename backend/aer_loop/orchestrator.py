from __future__ import annotations

from datetime import datetime
from typing import Any

from .agents import (
    AssertionAgent,
    CaseRouterAgent,
    CounterEvidenceAgent,
    InvestigationAgent,
    PassportAgent,
    PatternLearningAgent,
    PatternMatcherAgent,
    RiskSignalAgent,
    RouterAgent,
)
from .data import generate_demo_data
from .db import init_db, jdump, session
from .fusion import EvidenceFusionEngine
from .llm_client import LLMClient
from .policy import evidence_coverage
from .schemas import ActionName, AgentDecision, ToolObservation
from .tools import build_action_registry


class AERLoopOrchestrator:
    def __init__(self, con):
        self.con = con
        self.registry = build_action_registry(con)
        self.fusion = EvidenceFusionEngine(con)
        self.risk_signal_agent = RiskSignalAgent(con)
        self.pattern_matcher_agent = PatternMatcherAgent(con)
        self.case_router_agent = CaseRouterAgent(con)
        self.assertion_agent = AssertionAgent(con)
        self.router_agent = RouterAgent(con)
        self.investigation_agent = InvestigationAgent(con)
        self.counter_agent = CounterEvidenceAgent(con)
        self.passport_agent = PassportAgent(con)
        self.pattern_agent = PatternLearningAgent(con)

    def bootstrap(self, order_count: int | None = None, reset: bool = True) -> dict[str, Any]:
        init_db(self.con)
        stats = generate_demo_data(self.con, order_count=order_count, reset=reset)
        cases = self.fusion.build_candidate_cases()
        for case in cases:
            self.risk_signal_agent.assess_case(case["case_id"])
            self.pattern_matcher_agent.match_pattern(case["case_id"])
            self.case_router_agent.choose_depth(case["case_id"])
        return {"data": stats, "cases": cases}

    def run_case(self, case_id: str, max_steps: int = 8) -> dict[str, Any]:
        self.risk_signal_agent.assess_case(case_id)
        self.pattern_matcher_agent.match_pattern(case_id)
        route = self.case_router_agent.choose_depth(case_id)
        self.assertion_agent.build_assertion(case_id)
        observations: list[dict[str, Any]] = []
        executed: set[str] = set()
        route_max = int(route.get("max_steps", max_steps) or max_steps)
        if float(self._case_field(case_id, "risk_score", 0.0)) >= 0.72:
            route_max = max(route_max, 8)
        max_steps = min(max_steps, route_max)
        min_core_steps = self._min_core_steps(case_id, max_steps)
        for step in range(max_steps):
            available = self._available_actions_for_case(case_id, executed, allow_emit_passport=step + 1 >= min_core_steps)
            if not available:
                break
            decision = self.router_agent.route(case_id, available, executed=executed)
            observation = self.execute_decision(case_id, decision, agent_id="router_agent", step=step + 1)
            observations.append(observation.model_dump())
            executed.add(decision.action.value)
            self.investigation_agent.reflect_observation(case_id, decision, observation)

            cov = evidence_coverage(self.con, case_id)
            can_stop = step + 1 >= min_core_steps
            if can_stop and (decision.stop_after_action or decision.action == ActionName.emit_passport or observation.metrics.get("passport_ready") or cov.passport_ready):
                break

        evidence_dims = self._evidence_dimensions(case_id)
        if "counter_evidence" not in evidence_dims and not any(d.startswith("old_customer") or d.startswith("campus") for d in evidence_dims):
            decision = self.counter_agent.should_seek_counter(case_id)
            obs = self.execute_decision(case_id, decision, agent_id="counter_evidence_agent", step=len(observations) + 1)
            observations.append(obs.model_dump())
            self.investigation_agent.reflect_observation(case_id, decision, obs)

        passport = self.passport_agent.build_passport(case_id)
        self.pattern_agent.propose_candidate([case_id])
        return {
            "case_id": case_id,
            "observations": observations,
            "passport": passport.model_dump(),
            "trajectory_count": self.con.execute("SELECT COUNT(*) c FROM trajectory WHERE case_id=? OR case_id='PATTERN-LEARNING'", (case_id,)).fetchone()["c"],
            "evidence_count": self.con.execute("SELECT COUNT(*) c FROM evidence WHERE case_id=?", (case_id,)).fetchone()["c"],
        }

    def execute_decision(self, case_id: str, decision: AgentDecision, agent_id: str, step: int) -> ToolObservation:
        observation = self.registry.execute(decision.action, case_id, decision.params)
        self._record_thread(case_id, step, agent_id, decision, observation)
        return observation

    def _available_actions_for_case(self, case_id: str, executed: set[str], allow_emit_passport: bool = True) -> list[str]:
        ranked = self.registry.ranked_actions(case_id, executed=executed)
        actions = [item["action"] for item in ranked if item["action"] not in executed and item["action"] in self.registry.available_actions()]
        if not allow_emit_passport:
            actions = [action for action in actions if action != ActionName.emit_passport.value]
        cov = evidence_coverage(self.con, case_id)
        if allow_emit_passport and cov.passport_ready and ActionName.emit_passport.value not in actions and ActionName.emit_passport.value not in executed:
            actions.insert(0, ActionName.emit_passport.value)
        return actions

    def _min_core_steps(self, case_id: str, max_steps: int) -> int:
        required = self._case_field(case_id, "evidence_requirements", {})
        required_count = len(required) if isinstance(required, dict) else 0
        return min(max_steps, max(5, min(required_count, 8)))

    def _case_field(self, case_id: str, field: str, default: Any) -> Any:
        row = self.con.execute(f"SELECT {field} FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            return default
        value = row[field]
        if field == "evidence_requirements":
            from .db import jload

            return jload(value, default)
        return value

    def _evidence_dimensions(self, case_id: str) -> set[str]:
        rows = self.con.execute("SELECT dimension FROM evidence WHERE case_id=?", (case_id,)).fetchall()
        return {r["dimension"] for r in rows}

    def _record_thread(self, case_id: str, step: int, agent_id: str, decision: AgentDecision, observation: ToolObservation) -> None:
        self.con.execute(
            """
            INSERT INTO case_thread
            (case_id, thread_step, agent_id, action_taken, tool_params, observation_summary,
             support_evidence_delta, counter_evidence_delta, unresolved_conflicts, model_reasoning,
             policy_version, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                case_id,
                step,
                agent_id,
                decision.action.value,
                jdump(decision.params),
                observation.summary,
                jdump([e.evidence_id for e in observation.support_evidence]),
                jdump([e.evidence_id for e in observation.counter_evidence]),
                jdump([]),
                decision.reasoning,
                "aer_policy_v1_openclaw",
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )


def run_full_demo(order_count: int | None = None, max_steps: int = 8, reset: bool = True) -> dict[str, Any]:
    with session() as con:
        orchestrator = AERLoopOrchestrator(con)
        boot = orchestrator.bootstrap(order_count=order_count, reset=reset)
        case_results = []
        for case in boot["cases"]:
            case_results.append(orchestrator.run_case(case["case_id"], max_steps=max_steps))
        return {"bootstrap": boot, "case_results": case_results}
