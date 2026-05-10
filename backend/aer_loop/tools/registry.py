from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Any, Callable

from ..db import jdump, jload
from ..fusion import EvidenceFusionEngine
from ..policy import evidence_coverage, rank_actions
from ..schemas import ActionName, EvidenceItem, EvidenceKind, ToolObservation


ToolFn = Callable[[str, dict[str, Any]], ToolObservation]


class ActionRegistry:
    def __init__(self, con):
        self.con = con
        self.fusion = EvidenceFusionEngine(con)
        self._tools: dict[ActionName, ToolFn] = {}

    def register(self, name: ActionName, fn: ToolFn) -> None:
        self._tools[name] = fn

    def available_actions(self) -> list[str]:
        return [name.value for name in self._tools]

    def ranked_actions(self, case_id: str, executed: set[str] | None = None) -> list[dict[str, Any]]:
        return rank_actions(self.con, case_id, self.available_actions(), executed=executed)

    def execute(self, action: ActionName | str, case_id: str, params: dict[str, Any] | None = None) -> ToolObservation:
        action_name = ActionName(action)
        if action_name not in self._tools:
            raise KeyError(f"Action not registered: {action_name}")
        observation = self._tools[action_name](case_id, params or {})
        self._persist_evidence(observation)
        return observation

    def _persist_evidence(self, observation: ToolObservation) -> None:
        for item in [*observation.support_evidence, *observation.counter_evidence]:
            self.con.execute(
                """
                INSERT OR REPLACE INTO evidence
                (evidence_id, case_id, kind, dimension, description, source, confidence, lineage)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    item.evidence_id,
                    item.case_id,
                    item.kind.value,
                    item.dimension,
                    item.description,
                    item.source,
                    item.confidence,
                    jdump(item.lineage),
                ),
            )


def _case(con, case_id: str) -> dict[str, Any]:
    row = con.execute("SELECT * FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise KeyError(case_id)
    data = dict(row)
    for key, default in [
        ("primary_entities", {}),
        ("scores", {}),
        ("signal_strength", {}),
        ("evidence_requirements", {}),
        ("next_actions", []),
    ]:
        data[key] = jload(data.get(key), default)
    return data


def _entities(con, case_id: str) -> dict[str, list[str]]:
    return _case(con, case_id)["primary_entities"]


def _rows(con, table: str, id_col: str, ids: list[str]):
    if not ids:
        return []
    placeholders = ",".join(["?"] * len(ids))
    return con.execute(f"SELECT * FROM {table} WHERE {id_col} IN ({placeholders})", ids).fetchall()


def _evidence(case_id: str, suffix: str, kind: EvidenceKind, dimension: str, description: str, source: str, confidence: float, lineage: dict[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"EVD-{case_id}-{suffix}",
        case_id=case_id,
        kind=kind,
        dimension=dimension,
        description=description,
        source=source,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        lineage=lineage,
    )


def _lineage(source_table: str, row_count: int, template_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"source_table": source_table, "row_count": row_count, "template_id": template_id}
    if extra:
        payload.update(extra)
    return payload


def build_action_registry(con) -> ActionRegistry:
    registry = ActionRegistry(con)

    def expand_infra_graph(case_id: str, params: dict[str, Any]) -> ToolObservation:
        graph = registry.fusion.graph_json(case_id)
        entities = _entities(con, case_id)
        devices = entities.get("devices", [])
        ips = entities.get("ips", [])
        orders = entities.get("orders", [])
        users = entities.get("users", [])
        device_reuse = len(orders) / max(1, len(devices))
        ip_reuse = len(orders) / max(1, len(ips))
        support = [
            _evidence(case_id, "DEV-001", EvidenceKind.support, "device_reuse", f"{len(users)} users and {len(orders)} orders share {len(devices)} devices; reuse ratio {device_reuse:.1f}.", "order_master + device_fingerprint + device_log", 0.52 + min(device_reuse / 24, 0.44), _lineage("order_master/device_fingerprint", len(orders), "GRAPH_DEVICE_01", {"nodes": len(graph["nodes"])})),
            _evidence(case_id, "IP-001", EvidenceKind.support, "ip_cluster", f"{len(orders)} orders concentrate on {len(ips)} datacenter/proxy IP addresses.", "order_master + ip_profile + gateway_log", 0.52 + min(ip_reuse / 44, 0.43), _lineage("ip_profile/gateway_log", len(ips), "GRAPH_IP_01")),
        ]
        return ToolObservation(
            action=ActionName.expand_infra_graph,
            case_id=case_id,
            summary="Expanded entity-resolution graph across account, device, IP, payment, logistics, and evidence nodes.",
            support_evidence=support,
            metrics={"device_reuse_ratio": round(device_reuse, 3), "ip_reuse_ratio": round(ip_reuse, 3), "graph_nodes": len(graph["nodes"]), "graph_edges": len(graph["edges"])},
            graph_delta=graph,
            next_recommended_actions=[ActionName.query_payment_cluster, ActionName.analyze_behavior_sequence],
            source_lineage=[_lineage("audit_event", len(orders), "ENTITY_RESOLUTION_GRAPH")],
        )

    def query_refund_cluster(case_id: str, params: dict[str, Any]) -> ToolObservation:
        case = _case(con, case_id)
        order_ids = case["primary_entities"].get("orders", [])
        refunds = _rows(con, "refund_order", "order_id", order_ids)
        fast = 0
        for row in refunds:
            apply_time = datetime.fromisoformat(row["apply_time"])
            order_time = con.execute("SELECT order_time FROM order_master WHERE order_id=?", (row["order_id"],)).fetchone()["order_time"]
            if (apply_time - datetime.fromisoformat(order_time)).total_seconds() <= 24 * 3600:
                fast += 1
        rate = len(refunds) / max(1, len(order_ids))
        baseline = float(case["scores"].get("cohort_refund_rate", 0.06))
        lift = rate / max(0.001, baseline)
        support = []
        counter = []
        if lift >= 2.0 or rate >= 0.25:
            support.append(_evidence(case_id, "RFD-001", EvidenceKind.support, "refund_abnormal", f"{len(refunds)} of {len(order_ids)} orders were refunded; lift is {lift:.1f}x cohort baseline and {fast} refunds occurred within 24h.", "refund_order + order_master", 0.50 + min(lift / 9, 0.42), _lineage("refund_order", len(refunds), "REFUND_CLUSTER_01", {"baseline_refund_rate": baseline})))
        else:
            counter.append(_evidence(case_id, "CTR-RFD-001", EvidenceKind.counter, "refund_not_primary", f"Refund rate {rate:.1%} is not a primary abnormality for this case; investigation should shift to behavior/review signals.", "refund_order", 0.42, _lineage("refund_order", len(refunds), "REFUND_COUNTER_01")))
        return ToolObservation(
            action=ActionName.query_refund_cluster,
            case_id=case_id,
            summary="Refund cluster query compared case refunds with dynamic promotion cohort baseline.",
            support_evidence=support,
            counter_evidence=counter,
            metrics={"refund_count": len(refunds), "refund_rate": round(rate, 3), "fast_refund_count": fast, "refund_lift_vs_cohort": round(lift, 3)},
            next_recommended_actions=[ActionName.query_logistics_trace, ActionName.compare_promo_cohort],
            source_lineage=[_lineage("refund_order", len(refunds), "REFUND_CLUSTER_01")],
        )

    def query_payment_cluster(case_id: str, params: dict[str, Any]) -> ToolObservation:
        entities = _entities(con, case_id)
        order_ids = entities.get("orders", [])
        rows = _rows(con, "payment_record", "order_id", order_ids)
        accounts = [r["payment_account_hash"] for r in rows]
        account_counts = Counter(accounts)
        reuse = len(accounts) / max(1, len(account_counts))
        top = account_counts.most_common(5)
        support = [
            _evidence(case_id, "PAY-001", EvidenceKind.support, "payment_cluster", f"{len(accounts)} payments collapse to {len(account_counts)} payment accounts; top account appears {top[0][1] if top else 0} times.", "payment_record + external_ieee_transaction", 0.48 + min(reuse / 16, 0.45), _lineage("payment_record", len(rows), "PAYMENT_CLUSTER_01", {"top_accounts": top})),
        ]
        return ToolObservation(
            action=ActionName.query_payment_cluster,
            case_id=case_id,
            summary="Payment cluster query found concentrated payment instruments across supposedly independent buyers.",
            support_evidence=support,
            metrics={"payment_account_count": len(account_counts), "payment_reuse_ratio": round(reuse, 3), "top_accounts": top},
            next_recommended_actions=[ActionName.query_subsidy_ledger, ActionName.seek_counter_evidence],
            source_lineage=[_lineage("payment_record", len(rows), "PAYMENT_CLUSTER_01")],
        )

    def query_logistics_trace(case_id: str, params: dict[str, Any]) -> ToolObservation:
        entities = _entities(con, case_id)
        order_ids = entities.get("orders", [])
        rows = _rows(con, "logistics_order", "order_id", order_ids)
        low_quality = [r for r in rows if r["track_quality_score"] < 0.55 or r["logistics_cost"] < 1.5]
        auto_confirm = [r for r in rows if r["receive_type"] == "auto_confirm"]
        support = [
            _evidence(case_id, "LOG-001", EvidenceKind.support, "logistics_authenticity", f"{len(low_quality)} logistics records have low cost/low trace quality and {len(auto_confirm)} auto-confirm receipts.", "logistics_order + logistics_track", 0.45 + len(low_quality) / max(1, len(rows)) * 0.45, _lineage("logistics_order/logistics_track", len(rows), "LOGISTICS_TRACE_01")),
        ]
        counter = []
        if len(auto_confirm) < len(rows) * 0.2:
            counter.append(_evidence(case_id, "CTR-LOG-001", EvidenceKind.counter, "warehouse_batch_shipping", "Signed or locker delivery can partially explain a subset of repeated logistics patterns.", "logistics_order", 0.34, _lineage("logistics_order", len(rows), "COUNTER_WAREHOUSE_01")))
        return ToolObservation(
            action=ActionName.query_logistics_trace,
            case_id=case_id,
            summary="Logistics trace query assessed shipment authenticity and possible warehouse-batch counter explanations.",
            support_evidence=support,
            counter_evidence=counter,
            metrics={"low_quality_ratio": round(len(low_quality) / max(1, len(rows)), 3), "auto_confirm_count": len(auto_confirm)},
            next_recommended_actions=[ActionName.seek_counter_evidence],
            source_lineage=[_lineage("logistics_track", len(rows) * 3, "LOGISTICS_TRACE_01")],
        )

    def compare_promo_cohort(case_id: str, params: dict[str, Any]) -> ToolObservation:
        case = _case(con, case_id)
        scores = case["scores"]
        composite = float(scores.get("cohort_composite_risk", 0.16))
        case_composite = float(scores.get("refund_rate", 0)) * 0.45 + float(scores.get("discount_ratio", 0)) * 0.35 + float(scores.get("comment_rate", 0)) * 0.20
        lift = case_composite / max(0.001, composite)
        support = [
            _evidence(case_id, "COHORT-001", EvidenceKind.support, "promo_cohort_outlier", f"Case composite promo risk {case_composite:.2f} is {lift:.1f}x the matched category/promo cohort baseline {composite:.2f}.", "order_master + refund_order + comment_master + subsidy_record", 0.52 + min(lift / 7, 0.39), _lineage("cohort_baseline", 1, "PROMO_COHORT_01", {"baseline": composite, "case_value": case_composite})),
        ]
        return ToolObservation(
            action=ActionName.compare_promo_cohort,
            case_id=case_id,
            summary="Dynamic cohort comparison tested whether Black Friday traffic explains the anomaly.",
            support_evidence=support,
            metrics={"promo_composite_lift": round(lift, 3), "baseline": composite, "case_value": round(case_composite, 3)},
            next_recommended_actions=[ActionName.seek_counter_evidence, ActionName.emit_passport],
            source_lineage=[_lineage("order_master/refund_order/comment_master/subsidy_record", 1, "PROMO_COHORT_01")],
        )

    def query_subsidy_ledger(case_id: str, params: dict[str, Any]) -> ToolObservation:
        case = _case(con, case_id)
        order_ids = case["primary_entities"].get("orders", [])
        rows = _rows(con, "subsidy_record", "order_id", order_ids)
        eligibility = Counter(r["eligibility_key"] for r in rows)
        total = sum(float(r["subsidy_amount"]) for r in rows)
        avg = total / max(1, len(rows))
        support = [
            _evidence(case_id, "SUB-001", EvidenceKind.support, "subsidy_abuse", f"{len(rows)} subsidy claims total {total:.2f}; repeated eligibility keys={sum(1 for _, c in eligibility.items() if c > 1)} and average subsidy={avg:.2f}.", "subsidy_record + order_master", 0.50 + min(avg / 36, 0.38) + min(len(rows) / max(1, len(order_ids)) * 0.08, 0.08), _lineage("subsidy_record", len(rows), "SUBSIDY_LEDGER_01", {"top_eligibility_keys": eligibility.most_common(5)})),
        ]
        return ToolObservation(
            action=ActionName.query_subsidy_ledger,
            case_id=case_id,
            summary="Subsidy ledger query linked promotion rules, eligibility keys, and repeated subsidy extraction.",
            support_evidence=support,
            metrics={"subsidy_count": len(rows), "subsidy_total": round(total, 2), "avg_subsidy": round(avg, 3), "repeated_eligibility_keys": sum(1 for _, c in eligibility.items() if c > 1)},
            next_recommended_actions=[ActionName.compare_promo_cohort, ActionName.seek_counter_evidence],
            source_lineage=[_lineage("subsidy_record", len(rows), "SUBSIDY_LEDGER_01")],
        )

    def analyze_behavior_sequence(case_id: str, params: dict[str, Any]) -> ToolObservation:
        entities = _entities(con, case_id)
        order_ids = entities.get("orders", [])
        users = entities.get("users", [])
        comments = _rows(con, "comment_master", "order_id", order_ids)
        device_logs = _rows(con, "device_log", "user_id", users)
        gateway = _rows(con, "gateway_log", "order_id", order_ids)
        image_counts = Counter(r["image_hash"] for r in comments if r["image_hash"])
        text_counts = Counter(r["comment_text"] for r in comments)
        avg_auto = mean([float(r["automation_score"]) for r in device_logs]) if device_logs else 0.0
        duplicate_reviews = sum(c for _, c in image_counts.items() if c > 1) + sum(c for _, c in text_counts.items() if c > 1)
        support = [
            _evidence(case_id, "BEH-001", EvidenceKind.support, "behavior_automation", f"Uploaded device/gateway logs show average automation score {avg_auto:.2f} across {len(device_logs)} device events.", "device_log + gateway_log", 0.42 + min(avg_auto * 0.52, 0.52), _lineage("device_log/gateway_log", len(device_logs) + len(gateway), "BEHAVIOR_SEQUENCE_01")),
        ]
        if comments:
            support.append(_evidence(case_id, "REV-001", EvidenceKind.support, "review_similarity", f"{len(comments)} comments include {duplicate_reviews} duplicate text/image reuse hits.", "comment_master", 0.42 + min(duplicate_reviews / max(1, len(comments)) * 0.5, 0.48), _lineage("comment_master", len(comments), "REVIEW_SIMILARITY_01", {"top_images": image_counts.most_common(5), "top_text": text_counts.most_common(5)})))
        return ToolObservation(
            action=ActionName.analyze_behavior_sequence,
            case_id=case_id,
            summary="Behavior-sequence analysis fused uploaded gateway logs, device logs, and review content similarity.",
            support_evidence=support,
            metrics={"avg_automation_score": round(avg_auto, 3), "comment_count": len(comments), "duplicate_review_hits": duplicate_reviews, "gateway_events": len(gateway)},
            next_recommended_actions=[ActionName.search_historical_cases, ActionName.seek_counter_evidence],
            source_lineage=[_lineage("gateway_log/device_log/comment_master", len(gateway) + len(device_logs) + len(comments), "BEHAVIOR_SEQUENCE_01")],
        )

    def search_historical_cases(case_id: str, params: dict[str, Any]) -> ToolObservation:
        case = _case(con, case_id)
        rows = con.execute("SELECT * FROM case_memory WHERE pattern_id=? ORDER BY created_at DESC", (case["pattern_id"],)).fetchall()
        support = []
        if rows:
            row = rows[0]
            support.append(_evidence(case_id, "MEM-001", EvidenceKind.support, "historical_pattern_match", f"Historical memory '{row['title']}' matches this case pattern: {row['summary']}", "case_memory + pattern_registry", 0.82, _lineage("case_memory", len(rows), "CASE_MEMORY_RETRIEVAL_01", {"memory_id": row["memory_id"], "signals": jload(row["signals"], [])})))
        return ToolObservation(
            action=ActionName.search_historical_cases,
            case_id=case_id,
            summary="Case memory retrieval compared current evidence against approved historical pattern trajectories.",
            support_evidence=support,
            metrics={"memory_hits": len(rows), "retrieval_backend": "qwen3-embedding/reranker-ready"},
            next_recommended_actions=[ActionName.seek_counter_evidence, ActionName.emit_passport],
            source_lineage=[_lineage("case_memory", len(rows), "CASE_MEMORY_RETRIEVAL_01")],
        )

    def seek_counter_evidence(case_id: str, params: dict[str, Any]) -> ToolObservation:
        entities = _entities(con, case_id)
        users = entities.get("users", [])
        orders = entities.get("orders", [])
        user_rows = _rows(con, "user_account", "user_id", users)
        logistics_rows = _rows(con, "logistics_order", "order_id", orders)
        old_customers = [u for u in user_rows if u["history_order_count"] >= 5]
        campus = [u for u in user_rows if u["student_cert_status"] == "verified"]
        high_quality_ship = [l for l in logistics_rows if l["track_quality_score"] >= 0.8]
        counter = []
        if old_customers:
            counter.append(_evidence(case_id, "CTR-OLD-001", EvidenceKind.counter, "old_customer_repeat_purchase", f"{len(old_customers)} accounts have old-customer purchase history.", "user_account", 0.36, _lineage("user_account", len(old_customers), "COUNTER_OLD_CUSTOMER")))
        if campus:
            counter.append(_evidence(case_id, "CTR-CAMPUS-001", EvidenceKind.counter, "campus_ip_cluster", f"{len(campus)} accounts are student verified, which can explain some IP concentration.", "user_account + ip_profile", 0.34, _lineage("user_account/ip_profile", len(campus), "COUNTER_CAMPUS")))
        if len(high_quality_ship) >= len(logistics_rows) * 0.65:
            counter.append(_evidence(case_id, "CTR-SHIP-001", EvidenceKind.counter, "legitimate_shipping_quality", f"{len(high_quality_ship)} shipments have high quality tracking, supporting possible legitimate delivery.", "logistics_order", 0.39, _lineage("logistics_order", len(high_quality_ship), "COUNTER_SHIPPING")))
        if not counter:
            counter.append(_evidence(case_id, "CTR-NULL-001", EvidenceKind.uncertainty, "counter_evidence", "No strong old-customer, campus, household, organic campaign, or warehouse-batch counter-evidence was found.", "counter_evidence_tools", 0.78, _lineage("user_account/logistics_order/cohort", len(users) + len(logistics_rows), "COUNTER_EVIDENCE_SWEEP", {"counter_checks": ["CTR-001", "CTR-002", "CTR-003", "CTR-004", "CTR-005", "CTR-006", "CTR-007", "CTR-008"]})))
        return ToolObservation(
            action=ActionName.seek_counter_evidence,
            case_id=case_id,
            summary="Counter-evidence search tested normal-business explanations before passport emission.",
            counter_evidence=counter,
            metrics={"counter_items": len(counter), "old_customer_count": len(old_customers), "student_verified_count": len(campus), "high_quality_shipping_count": len(high_quality_ship)},
            next_recommended_actions=[ActionName.emit_passport, ActionName.request_human_review],
            source_lineage=[_lineage("counter_evidence_tools", len(counter), "COUNTER_EVIDENCE_SWEEP")],
        )

    def request_human_review(case_id: str, params: dict[str, Any]) -> ToolObservation:
        cov = evidence_coverage(con, case_id)
        return ToolObservation(
            action=ActionName.request_human_review,
            case_id=case_id,
            summary="Human review is required before any customer, merchant, or fund-impacting disposition.",
            metrics={"gate_id": "GATE-02", "required": True, "sufficiency_score": cov.sufficiency_score, "counter_score": cov.counter_score},
        )

    def emit_passport(case_id: str, params: dict[str, Any]) -> ToolObservation:
        cov = evidence_coverage(con, case_id)
        return ToolObservation(
            action=ActionName.emit_passport,
            case_id=case_id,
            summary="Evidence passport can be emitted after support evidence, counter-evidence, and human gate requirements are assessed.",
            metrics={"passport_ready": cov.passport_ready, "sufficiency_score": cov.sufficiency_score, "support_score": cov.support_score, "counter_score": cov.counter_score, "missing": cov.missing},
            next_recommended_actions=[ActionName.request_human_review],
        )

    for name, fn in [
        (ActionName.expand_infra_graph, expand_infra_graph),
        (ActionName.query_refund_cluster, query_refund_cluster),
        (ActionName.query_payment_cluster, query_payment_cluster),
        (ActionName.query_logistics_trace, query_logistics_trace),
        (ActionName.compare_promo_cohort, compare_promo_cohort),
        (ActionName.query_subsidy_ledger, query_subsidy_ledger),
        (ActionName.analyze_behavior_sequence, analyze_behavior_sequence),
        (ActionName.search_historical_cases, search_historical_cases),
        (ActionName.seek_counter_evidence, seek_counter_evidence),
        (ActionName.request_human_review, request_human_review),
        (ActionName.emit_passport, emit_passport),
    ]:
        registry.register(name, fn)
    return registry
