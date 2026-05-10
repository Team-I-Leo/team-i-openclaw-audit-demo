from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import ensure_runtime_dirs, settings
from ..db import init_db, jdump, jload, session
from ..fusion import EvidenceFusionEngine
from ..orchestrator import AERLoopOrchestrator, run_full_demo
from ..policy import ACTION_DIMENSIONS, evidence_coverage
from ..schemas import ActionName, AgentDecision


class ReviewRequest(BaseModel):
    decision: str
    note: str = ""
    reviewer: str = "demo_auditor"


class StepRequest(BaseModel):
    action: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class IngestBatchRequest(BaseModel):
    source_system: str
    source_table: str
    entity_type: str
    rows: list[dict[str, Any]]
    case_hint: str = ""


class CandidatePatternRequest(BaseModel):
    case_ids: list[str] = Field(default_factory=list)


class CandidatePatternReviewRequest(BaseModel):
    decision: str
    note: str = ""
    reviewer: str = "demo_auditor"


ensure_runtime_dirs()
app = FastAPI(title="Team-I OpenCLAW Audit Demo", version="0.1.0")
static_dir = Path(__file__).resolve().parents[1] / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
def _startup() -> None:
    with session() as con:
        init_db(con)


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")


@app.post("/api/demo/bootstrap")
def demo_bootstrap(order_count: int | None = None, reset: bool = True):
    with session() as con:
        orch = AERLoopOrchestrator(con)
        return orch.bootstrap(order_count=order_count, reset=reset)


@app.post("/api/demo/run")
def demo_run(order_count: int | None = None, max_steps: int = 8, reset: bool = True):
    return run_full_demo(order_count=order_count, max_steps=max_steps, reset=reset)


@app.get("/api/dashboard")
def dashboard():
    with session() as con:
        case_count = con.execute("SELECT COUNT(*) c FROM risk_case").fetchone()["c"]
        evidence_count = con.execute("SELECT COUNT(*) c FROM evidence").fetchone()["c"]
        trajectory_count = con.execute("SELECT COUNT(*) c FROM trajectory").fetchone()["c"]
        passport_count = con.execute("SELECT COUNT(*) c FROM passport").fetchone()["c"]
        risk_levels = [dict(r) for r in con.execute("SELECT risk_level, COUNT(*) count FROM risk_case GROUP BY risk_level").fetchall()]
        actions = [dict(r) for r in con.execute("SELECT action_taken action, COUNT(*) count FROM case_thread GROUP BY action_taken").fetchall()]
        return {
            "case_count": case_count,
            "evidence_count": evidence_count,
            "trajectory_count": trajectory_count,
            "passport_count": passport_count,
            "risk_levels": risk_levels,
            "actions": actions,
            "model_backend": settings.model_backend,
            "model_path": settings.model_path,
            "openclaw_gateway_url": settings.openclaw_gateway_url,
            "model_invocations": [dict(r) for r in con.execute("SELECT agent_id, backend, model, used_fallback, COUNT(*) count FROM model_invocation GROUP BY agent_id, backend, model, used_fallback ORDER BY agent_id").fetchall()],
        }


@app.get("/api/cases")
def cases():
    with session() as con:
        rows = con.execute("SELECT * FROM risk_case ORDER BY risk_score DESC").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["primary_entities"] = jload(item["primary_entities"], {})
            item["scores"] = jload(item["scores"], {})
            item["next_actions"] = jload(item["next_actions"], [])
            out.append(item)
        return out


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    with session() as con:
        row = con.execute("SELECT * FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="case not found")
        item = dict(row)
        item["primary_entities"] = jload(item["primary_entities"], {})
        item["scores"] = jload(item["scores"], {})
        item["next_actions"] = jload(item["next_actions"], [])
        item["evidence"] = [_decode_evidence(dict(r)) for r in con.execute("SELECT * FROM evidence WHERE case_id=? ORDER BY evidence_id", (case_id,)).fetchall()]
        item["thread"] = [_decode_thread(dict(r)) for r in con.execute("SELECT * FROM case_thread WHERE case_id=? ORDER BY id", (case_id,)).fetchall()]
        item["trajectory"] = [_decode_trajectory(dict(r)) for r in con.execute("SELECT * FROM trajectory WHERE case_id=? ORDER BY id", (case_id,)).fetchall()]
        return item


@app.post("/api/cases/{case_id}/step")
def case_step(case_id: str, body: StepRequest):
    with session() as con:
        orch = AERLoopOrchestrator(con)
        if body.action:
            decision = AgentDecision(action=body.action, reasoning="Manual demo step through governed action.", params=body.params)
        else:
            decision = orch.router_agent.route(case_id, orch._available_actions_for_case(case_id, set()))
        obs = orch.execute_decision(case_id, decision, agent_id="api_step", step=_next_step(con, case_id))
        orch.investigation_agent.reflect_observation(case_id, decision, obs)
        return obs.model_dump()


@app.post("/api/cases/{case_id}/run")
def case_run(case_id: str, max_steps: int = 8):
    with session() as con:
        return AERLoopOrchestrator(con).run_case(case_id, max_steps=max_steps)


@app.get("/api/cases/{case_id}/graph")
def case_graph(case_id: str):
    with session() as con:
        return EvidenceFusionEngine(con).graph_json(case_id)


@app.get("/api/cases/{case_id}/route")
def case_route(case_id: str):
    with session() as con:
        orch = AERLoopOrchestrator(con)
        cov = evidence_coverage(con, case_id)
        return {
            "case_id": case_id,
            "coverage": {
                "required": cov.required,
                "covered": cov.covered,
                "missing": cov.missing,
                "support_score": cov.support_score,
                "counter_score": cov.counter_score,
                "sufficiency_score": cov.sufficiency_score,
                "passport_ready": cov.passport_ready,
            },
            "ranked_actions": orch.registry.ranked_actions(case_id),
        }


@app.get("/api/cases/{case_id}/passport")
def case_passport(case_id: str):
    with session() as con:
        row = con.execute("SELECT passport_json FROM passport WHERE case_id=?", (case_id,)).fetchone()
        if row:
            return json.loads(row["passport_json"])
        passport = AERLoopOrchestrator(con).passport_agent.build_passport(case_id)
        return passport.model_dump()


@app.post("/api/cases/{case_id}/review")
def submit_review(case_id: str, body: ReviewRequest):
    with session() as con:
        con.execute(
            "INSERT INTO human_review (case_id, decision, note, reviewer, created_at) VALUES (?,?,?,?,?)",
            (case_id, body.decision, body.note, body.reviewer, datetime.utcnow().isoformat(timespec="seconds")),
        )
        con.execute("UPDATE risk_case SET status=? WHERE case_id=?", (f"reviewed:{body.decision}", case_id))
        return {"ok": True, "case_id": case_id, "decision": body.decision}


@app.get("/api/patterns")
def patterns():
    with session() as con:
        rows = con.execute("SELECT * FROM risk_pattern ORDER BY pattern_id").fetchall()
        return [{**dict(r), "definition": jload(r["definition"], {})} for r in rows]


@app.get("/api/patterns/candidates")
def candidates():
    with session() as con:
        rows = con.execute("SELECT * FROM candidate_pattern ORDER BY created_at DESC").fetchall()
        return [
            _decode_candidate_pattern(dict(r))
            for r in rows
        ]


@app.post("/api/patterns/candidate")
def propose_candidate(body: CandidatePatternRequest):
    with session() as con:
        orch = AERLoopOrchestrator(con)
        case_ids = body.case_ids or [r["case_id"] for r in con.execute("SELECT case_id FROM risk_case ORDER BY risk_score DESC").fetchall()]
        return orch.pattern_agent.propose_candidate(case_ids)


@app.post("/api/patterns/candidates/{candidate_id}/review")
def review_candidate_pattern(candidate_id: str, body: CandidatePatternReviewRequest):
    decision = _normalize_pattern_review_decision(body.decision)
    now = datetime.utcnow().isoformat(timespec="seconds")
    with session() as con:
        row = con.execute("SELECT * FROM candidate_pattern WHERE candidate_id=?", (candidate_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="candidate pattern not found")
        candidate = _decode_candidate_pattern(dict(row))
        status = "approved" if decision == "approve" else "rejected"
        con.execute("UPDATE candidate_pattern SET status=? WHERE candidate_id=?", (status, candidate_id))
        con.execute(
            "INSERT INTO human_review (case_id, decision, note, reviewer, created_at) VALUES (?,?,?,?,?)",
            (f"PATTERN:{candidate_id}", status, body.note, body.reviewer, now),
        )
        if decision == "reject":
            return {"ok": True, "candidate_id": candidate_id, "status": status}
        promoted = _promote_candidate_pattern(con, candidate, body, now)
        return {"ok": True, "candidate_id": candidate_id, "status": status, **promoted}


@app.get("/api/policy/weights")
def policy_weights():
    with session() as con:
        rows = con.execute("SELECT * FROM policy_action_weight ORDER BY updated_at DESC, pattern_id, action_name").fetchall()
        return [dict(r) for r in rows]


@app.post("/api/ingest/batch")
def ingest_batch(body: IngestBatchRequest):
    with session() as con:
        now = datetime.utcnow().isoformat(timespec="seconds")
        for idx, row in enumerate(body.rows):
            entity_id = str(row.get("id") or row.get("order_id") or row.get("event_id") or row.get("transaction_id") or f"row-{idx}")
            event_time = str(row.get("event_time") or row.get("order_time") or row.get("created_at") or now)
            con.execute(
                "INSERT OR REPLACE INTO audit_event VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"ING-{body.source_table}-{abs(hash((entity_id, idx, now))) % 10_000_000:07d}",
                    body.source_system,
                    body.source_table,
                    body.entity_type,
                    entity_id,
                    event_time,
                    body.case_hint,
                    jdump(row),
                ),
            )
        return {"ok": True, "ingested": len(body.rows), "source_system": body.source_system, "source_table": body.source_table}


@app.get("/api/stream/events")
def event_stream():
    def _events():
        with session() as con:
            payload = {
                "type": "snapshot",
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "cases": con.execute("SELECT COUNT(*) c FROM risk_case").fetchone()["c"],
                "evidence": con.execute("SELECT COUNT(*) c FROM evidence").fetchone()["c"],
                "trajectories": con.execute("SELECT COUNT(*) c FROM trajectory").fetchone()["c"],
            }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(_events(), media_type="text/event-stream")


@app.post("/api/openclaw/tools/{action_name}")
def openclaw_tool(action_name: str, payload: dict[str, Any]):
    case_id = payload.get("case_id", "AER-001")
    params = payload.get("params", {})
    with session() as con:
        obs = AERLoopOrchestrator(con).registry.execute(action_name, case_id, params)
        return obs.model_dump()


@app.post("/api/openclaw/session/run")
def openclaw_session_run(payload: dict[str, Any]):
    case_id = payload.get("case_id", "AER-001")
    max_steps = int(payload.get("max_steps", 10))
    with session() as con:
        result = AERLoopOrchestrator(con).run_case(case_id, max_steps=max_steps)
        return {"ok": True, "runtime": "openclaw-compatible-session", "case_id": case_id, "result": result}


def _normalize_pattern_review_decision(decision: str) -> str:
    normalized = decision.strip().lower()
    if normalized in {"approve", "approved", "accept", "accepted", "pass", "passed", "通过", "批准"}:
        return "approve"
    if normalized in {"reject", "rejected", "deny", "denied", "fail", "failed", "拒绝", "驳回"}:
        return "reject"
    raise HTTPException(status_code=400, detail="decision must be approve or reject")


def _decode_candidate_pattern(item: dict[str, Any]) -> dict[str, Any]:
    item["supporting_cases"] = jload(item.get("supporting_cases"), [])
    item["common_signals"] = jload(item.get("common_signals"), [])
    item["required_counter_checks"] = jload(item.get("required_counter_checks"), [])
    return item


def _promote_candidate_pattern(con, candidate: dict[str, Any], body: CandidatePatternReviewRequest, now: str) -> dict[str, Any]:
    candidate_id = candidate["candidate_id"]
    promoted_pattern_id = _promoted_pattern_id(con, candidate_id)
    supporting_cases = [str(case_id) for case_id in candidate.get("supporting_cases", [])]
    common_signals = [str(signal) for signal in candidate.get("common_signals", [])]
    required_counter_checks = [str(check) for check in candidate.get("required_counter_checks", [])]
    case_rows = _rows_for_ids(con, "risk_case", "case_id", supporting_cases)
    target_pattern_ids = sorted({row["pattern_id"] for row in case_rows}) or [candidate_id]
    action_boosts = _candidate_action_boosts(common_signals, required_counter_checks)
    support_count = max(1, len(supporting_cases))

    definition = {
        "source": "pattern_learning_agent",
        "source_candidate_id": candidate_id,
        "supporting_cases": supporting_cases,
        "common_signals": common_signals,
        "required_counter_checks": required_counter_checks,
        "policy_learning": {
            "target_pattern_ids": target_pattern_ids,
            "action_boosts": action_boosts,
            "support_count": support_count,
        },
        "human_approval": {
            "decision": "approved",
            "reviewer": body.reviewer,
            "note": body.note,
            "approved_at": now,
        },
    }
    con.execute(
        "INSERT OR REPLACE INTO risk_pattern VALUES (?,?,?,?,?)",
        (promoted_pattern_id, candidate.get("name", promoted_pattern_id), f"learned:{now}", "approved", jdump(definition)),
    )

    policy_targets = sorted(set(target_pattern_ids + [promoted_pattern_id]))
    for pattern_id in policy_targets:
        for action_name, weight_delta in action_boosts.items():
            con.execute(
                """
                INSERT INTO policy_action_weight
                (pattern_id, action_name, weight_delta, support_count, source_candidate_id, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(pattern_id, action_name, source_candidate_id)
                DO UPDATE SET
                    weight_delta=excluded.weight_delta,
                    support_count=excluded.support_count,
                    updated_at=excluded.updated_at
                """,
                (pattern_id, action_name, float(weight_delta), support_count, candidate_id, now),
            )

    memory_ids = _write_candidate_case_memory(
        con=con,
        candidate=candidate,
        case_rows=case_rows,
        target_pattern_ids=policy_targets,
        action_boosts=action_boosts,
        reviewer=body.reviewer,
        note=body.note,
        now=now,
    )
    return {
        "risk_pattern_id": promoted_pattern_id,
        "policy_weight_updates": [
            {"pattern_id": pattern_id, "action_name": action_name, "weight_delta": weight_delta}
            for pattern_id in policy_targets
            for action_name, weight_delta in action_boosts.items()
        ],
        "case_memory_ids": memory_ids,
    }


def _promoted_pattern_id(con, candidate_id: str) -> str:
    existing = con.execute("SELECT 1 FROM risk_pattern WHERE pattern_id=?", (candidate_id,)).fetchone()
    if existing and not candidate_id.startswith(("CAND-", "LEARNED-")):
        return f"LEARNED-{candidate_id}"
    return candidate_id


def _write_candidate_case_memory(
    con,
    candidate: dict[str, Any],
    case_rows: list[Any],
    target_pattern_ids: list[str],
    action_boosts: dict[str, float],
    reviewer: str,
    note: str,
    now: str,
) -> list[str]:
    candidate_id = candidate["candidate_id"]
    common_signals = [str(signal) for signal in candidate.get("common_signals", [])]
    required_counter_checks = [str(check) for check in candidate.get("required_counter_checks", [])]
    supporting_cases = [str(case_id) for case_id in candidate.get("supporting_cases", [])]
    case_names = sorted({row["pattern_name"] for row in case_rows})
    summary = (
        f"Approved learned pattern from {', '.join(supporting_cases) or 'selected cases'}; "
        f"signals={', '.join(common_signals) or 'n/a'}; counter_checks={', '.join(required_counter_checks) or 'n/a'}."
    )
    resolution = f"Human-approved by {reviewer}. {note}".strip()
    payload = {
        "supporting_cases": supporting_cases,
        "source_candidate_id": candidate_id,
        "source_case_patterns": case_names,
        "policy_action_boosts": action_boosts,
    }
    memory_ids: list[str] = []
    for pattern_id in target_pattern_ids:
        memory_id = f"MEM-{candidate_id}-{pattern_id}".replace(":", "-")
        con.execute(
            "INSERT OR REPLACE INTO case_memory VALUES (?,?,?,?,?,?,?,?)",
            (
                memory_id,
                pattern_id,
                f"Approved learned memory: {candidate.get('name', candidate_id)}",
                f"{summary} metadata={json.dumps(payload, ensure_ascii=False)}",
                jdump(common_signals),
                jdump(required_counter_checks),
                resolution,
                now,
            ),
        )
        memory_ids.append(memory_id)
    return memory_ids


def _candidate_action_boosts(common_signals: list[str], required_counter_checks: list[str]) -> dict[str, float]:
    dims = {_canonical_signal_dim(signal) for signal in common_signals}
    dims.discard("")
    boosts: dict[str, float] = {}
    for action_name, action_dims in ACTION_DIMENSIONS.items():
        overlap = dims.intersection(action_dims)
        if overlap:
            boosts[action_name] = round(min(0.16, 0.05 + 0.035 * len(overlap)), 3)
    if required_counter_checks:
        boosts[ActionName.seek_counter_evidence.value] = max(boosts.get(ActionName.seek_counter_evidence.value, 0.0), 0.11)
        boosts[ActionName.request_human_review.value] = max(boosts.get(ActionName.request_human_review.value, 0.0), 0.04)
    if not boosts:
        boosts[ActionName.search_historical_cases.value] = 0.05
    return dict(sorted(boosts.items()))


def _canonical_signal_dim(signal: str) -> str:
    text = signal.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "shared_device": "device_reuse",
        "device_cluster": "device_reuse",
        "device_reuse": "device_reuse",
        "shared_ip": "ip_cluster",
        "ip_reuse": "ip_cluster",
        "ip_cluster": "ip_cluster",
        "shared_payment": "payment_cluster",
        "payment_reuse": "payment_cluster",
        "payment_cluster": "payment_cluster",
        "refund_under_24h": "refund_abnormal",
        "fast_refund": "refund_abnormal",
        "refund_abnormal": "refund_abnormal",
        "low_quality_logistics": "logistics_authenticity",
        "logistics_authenticity": "logistics_authenticity",
        "promo_outlier": "promo_cohort_outlier",
        "promo_cohort_outlier": "promo_cohort_outlier",
        "subsidy_abuse": "subsidy_abuse",
        "review_similarity": "review_similarity",
        "duplicate_review": "review_similarity",
        "behavior_automation": "behavior_automation",
        "automation": "behavior_automation",
        "historical_pattern_match": "historical_pattern_match",
    }
    if text in aliases:
        return aliases[text]
    for known in aliases:
        if known in text:
            return aliases[known]
    return text if any(text in dims for dims in ACTION_DIMENSIONS.values()) else ""


def _rows_for_ids(con, table: str, id_col: str, ids: list[str]):
    if not ids:
        return []
    placeholders = ",".join(["?"] * len(ids))
    return con.execute(f"SELECT * FROM {table} WHERE {id_col} IN ({placeholders})", ids).fetchall()


def _next_step(con, case_id: str) -> int:
    row = con.execute("SELECT MAX(thread_step) m FROM case_thread WHERE case_id=?", (case_id,)).fetchone()
    return int(row["m"] or 0) + 1


def _decode_evidence(item: dict[str, Any]) -> dict[str, Any]:
    item["lineage"] = jload(item.get("lineage"), {})
    return item


def _decode_thread(item: dict[str, Any]) -> dict[str, Any]:
    for key in ["tool_params", "support_evidence_delta", "counter_evidence_delta", "unresolved_conflicts"]:
        item[key] = jload(item.get(key), [] if key != "tool_params" else {})
    return item


def _decode_trajectory(item: dict[str, Any]) -> dict[str, Any]:
    for key in ["state_json", "decision_json", "observation_json", "reward_json"]:
        item[key] = jload(item.get(key), {})
    return item
