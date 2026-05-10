from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

import networkx as nx

from .db import jdump, jload
from .schemas import ActionName


PATTERN_NAMES = {
    "EC-SKIM-001": "Shared infrastructure brushing and subsidy skimming",
    "EC-FAKE-002": "Review farming and reputation manipulation",
    "EC-ARBI-003": "Promotion subsidy arbitrage and refund extraction",
}


REQUIRED_EVIDENCE = {
    "EC-SKIM-001": {
        "device_reuse": 0.14,
        "ip_cluster": 0.12,
        "payment_cluster": 0.12,
        "refund_abnormal": 0.14,
        "logistics_authenticity": 0.12,
        "promo_cohort_outlier": 0.12,
        "subsidy_abuse": 0.10,
        "behavior_automation": 0.08,
        "counter_evidence": 0.06,
    },
    "EC-FAKE-002": {
        "device_reuse": 0.10,
        "ip_cluster": 0.10,
        "review_similarity": 0.20,
        "behavior_automation": 0.16,
        "payment_cluster": 0.10,
        "logistics_authenticity": 0.08,
        "promo_cohort_outlier": 0.08,
        "historical_pattern_match": 0.10,
        "counter_evidence": 0.08,
    },
    "EC-ARBI-003": {
        "subsidy_abuse": 0.18,
        "payment_cluster": 0.14,
        "refund_abnormal": 0.14,
        "device_reuse": 0.10,
        "ip_cluster": 0.10,
        "logistics_authenticity": 0.10,
        "promo_cohort_outlier": 0.14,
        "counter_evidence": 0.10,
    },
}


def _ratio(numer: float, denom: float) -> float:
    return numer / max(1.0, denom)


def _strength(value: float) -> str:
    if value >= 0.78:
        return "strong"
    if value >= 0.52:
        return "medium"
    if value >= 0.28:
        return "weak"
    return "none"


class EvidenceFusionEngine:
    def __init__(self, con):
        self.con = con

    def build_candidate_cases(self) -> list[dict[str, Any]]:
        cases = []
        for pattern_id in ["EC-SKIM-001", "EC-FAKE-002", "EC-ARBI-003"]:
            if self.con.execute("SELECT COUNT(*) c FROM order_master WHERE fraud_type=?", (pattern_id,)).fetchone()["c"]:
                cases.append(self._build_case(pattern_id))
        for case in cases:
            self._upsert_case(case)
        return cases

    def _build_case(self, pattern_id: str) -> dict[str, Any]:
        rows = self.con.execute("SELECT * FROM order_master WHERE fraud_type=? ORDER BY order_time", (pattern_id,)).fetchall()
        if not rows:
            raise RuntimeError(f"No seeded {pattern_id} orders found. Run data generation first.")

        order_ids = [r["order_id"] for r in rows]
        user_ids = sorted({r["user_id"] for r in rows})
        device_ids = sorted({r["device_id"] for r in rows})
        ip_addresses = sorted({r["ip_address"] for r in rows})
        merchant_ids = sorted({r["merchant_id"] for r in rows})
        payment_rows = self._rows_by_ids("payment_record", "order_id", order_ids)
        refund_rows = self._rows_by_ids("refund_order", "order_id", order_ids)
        logistics_rows = self._rows_by_ids("logistics_order", "order_id", order_ids)
        comment_rows = self._rows_by_ids("comment_master", "order_id", order_ids)
        subsidy_rows = self._rows_by_ids("subsidy_record", "order_id", order_ids)
        gateway_rows = self._rows_by_ids("gateway_log", "order_id", order_ids)
        device_log_rows = self._rows_by_ids("device_log", "user_id", user_ids)
        ieee_rows = self._rows_by_ids("external_ieee_transaction", "order_id", order_ids)

        payment_accounts = [r["payment_account_hash"] for r in payment_rows]
        image_hashes = [r["image_hash"] for r in comment_rows if r["image_hash"]]
        comment_texts = [r["comment_text"] for r in comment_rows]
        logistics_quality = [float(r["track_quality_score"]) for r in logistics_rows]
        automation_scores = [float(r["automation_score"]) for r in device_log_rows]
        subsidy_amounts = [float(r["subsidy_amount"]) for r in subsidy_rows]
        pay_amounts = [float(r["pay_amount"]) for r in rows]
        discount_amounts = [float(r["discount_amount"]) for r in rows]

        category = rows[0]["category_id"]
        promo = rows[0]["promo_event_id"]
        cohort = self._cohort_baseline(category, promo)

        device_reuse = len(rows) / max(1, len(device_ids))
        ip_reuse = len(rows) / max(1, len(ip_addresses))
        payment_reuse = len(payment_accounts) / max(1, len(set(payment_accounts)))
        refund_rate = len(refund_rows) / len(rows)
        comment_rate = len(comment_rows) / len(rows)
        duplicate_image_rate = _ratio(len(image_hashes), len(set(image_hashes)))
        duplicate_text_rate = _ratio(len(comment_texts), len(set(comment_texts)))
        low_logistics_rate = len([q for q in logistics_quality if q < 0.55]) / max(1, len(logistics_quality))
        avg_automation = mean(automation_scores) if automation_scores else 0.0
        avg_subsidy = mean(subsidy_amounts) if subsidy_amounts else 0.0
        subsidy_rate = len(subsidy_rows) / len(rows)
        discount_ratio = sum(discount_amounts) / max(1.0, sum(pay_amounts) + sum(discount_amounts))
        ieee_fraud_rate = sum(int(r["fraud_label"]) for r in ieee_rows) / max(1, len(ieee_rows))

        signal_values = {
            "device_reuse": min(1.0, device_reuse / 18),
            "ip_cluster": min(1.0, ip_reuse / 34),
            "payment_cluster": min(1.0, payment_reuse / 14),
            "refund_abnormal": min(1.0, refund_rate / max(0.03, cohort["refund_rate"] * 4)),
            "logistics_authenticity": min(1.0, low_logistics_rate * 1.15),
            "promo_cohort_outlier": min(1.0, (refund_rate + discount_ratio + subsidy_rate) / max(0.01, cohort["composite_risk"] * 3)),
            "subsidy_abuse": min(1.0, subsidy_rate * 0.45 + min(avg_subsidy / 24, 0.45) + min(discount_ratio, 0.45)),
            "review_similarity": min(1.0, duplicate_image_rate / 18 + duplicate_text_rate / 18 + comment_rate * 0.25),
            "behavior_automation": min(1.0, avg_automation),
            "historical_pattern_match": 0.82,
            "external_feature_anomaly": ieee_fraud_rate,
        }

        req = REQUIRED_EVIDENCE[pattern_id]
        weighted = sum(signal_values.get(dim, 0.0) * weight for dim, weight in req.items() if dim != "counter_evidence")
        score_s = min(1.0, signal_values["refund_abnormal"] * 0.34 + signal_values["promo_cohort_outlier"] * 0.26 + signal_values["subsidy_abuse"] * 0.25 + signal_values["external_feature_anomaly"] * 0.15)
        score_r = min(1.0, signal_values["device_reuse"] * 0.30 + signal_values["ip_cluster"] * 0.25 + signal_values["payment_cluster"] * 0.25 + low_logistics_rate * 0.20)
        score_n = min(1.0, signal_values["review_similarity"] * 0.35 + signal_values["behavior_automation"] * 0.35 + signal_values["historical_pattern_match"] * 0.15 + comment_rate * 0.15)
        risk_score = round(min(0.99, 0.22 + weighted + 0.18 * score_s + 0.16 * score_r + 0.12 * score_n), 3)

        assertions = {
            "EC-SKIM-001": "AER-001 detects new-account subsidy skimming: shared devices/IPs/payment accounts, fast refunds, low-quality logistics, and weak normal-business counter explanations.",
            "EC-FAKE-002": "AER-002 detects reputation manipulation: repeated micro-orders, duplicate review text/images, automation signals, shared infrastructure, and merchant-level rating inflation.",
            "EC-ARBI-003": "AER-003 detects subsidy arbitrage: concentrated eligibility keys and payment accounts repeatedly extract high discounts with abnormal refund/logistics patterns.",
        }
        case_id = {"EC-SKIM-001": "AER-001", "EC-FAKE-002": "AER-002", "EC-ARBI-003": "AER-003"}[pattern_id]
        return {
            "case_id": case_id,
            "pattern_id": pattern_id,
            "pattern_name": PATTERN_NAMES[pattern_id],
            "risk_level": "critical" if risk_score >= 0.86 else "high" if risk_score >= 0.72 else "medium",
            "risk_score": risk_score,
            "assertion": assertions[pattern_id],
            "status": "investigation_ready",
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            "primary_entities": {
                "orders": order_ids,
                "users": user_ids,
                "devices": device_ids,
                "ips": ip_addresses,
                "merchants": merchant_ids,
                "payment_accounts": sorted(set(payment_accounts)),
            },
            "scores": {
                "statistical": round(score_s, 3),
                "relational": round(score_r, 3),
                "narrative_behavior": round(score_n, 3),
                "device_reuse": round(device_reuse, 3),
                "ip_reuse": round(ip_reuse, 3),
                "refund_rate": round(refund_rate, 3),
                "payment_reuse": round(payment_reuse, 3),
                "comment_rate": round(comment_rate, 3),
                "duplicate_image_rate": round(duplicate_image_rate, 3),
                "duplicate_text_rate": round(duplicate_text_rate, 3),
                "low_logistics_rate": round(low_logistics_rate, 3),
                "avg_automation_score": round(avg_automation, 3),
                "avg_subsidy": round(avg_subsidy, 3),
                "subsidy_rate": round(subsidy_rate, 3),
                "discount_ratio": round(discount_ratio, 3),
                "cohort_refund_rate": round(cohort["refund_rate"], 3),
                "cohort_composite_risk": round(cohort["composite_risk"], 3),
                "ieee_fraud_rate": round(ieee_fraud_rate, 3),
            },
            "signal_strength": {dim: _strength(value) for dim, value in signal_values.items()},
            "evidence_requirements": req,
            "next_actions": self.initial_actions(pattern_id),
        }

    def initial_actions(self, pattern_id: str) -> list[str]:
        actions = [
            ActionName.expand_infra_graph.value,
            ActionName.query_payment_cluster.value,
            ActionName.query_logistics_trace.value,
            ActionName.compare_promo_cohort.value,
            ActionName.analyze_behavior_sequence.value,
            ActionName.search_historical_cases.value,
            ActionName.seek_counter_evidence.value,
        ]
        if pattern_id in {"EC-SKIM-001", "EC-ARBI-003"}:
            actions.insert(1, ActionName.query_refund_cluster.value)
            actions.insert(2, ActionName.query_subsidy_ledger.value)
        return actions

    def _cohort_baseline(self, category_id: str, promo_event_id: str) -> dict[str, float]:
        rows = self.con.execute(
            """
            SELECT o.order_id, o.pay_amount, o.discount_amount
            FROM order_master o
            WHERE o.category_id=? AND o.promo_event_id=? AND o.fraud_type='normal'
            LIMIT 5000
            """,
            (category_id, promo_event_id),
        ).fetchall()
        if not rows:
            return {"refund_rate": 0.06, "comment_rate": 0.42, "discount_ratio": 0.08, "composite_risk": 0.16}
        order_ids = [r["order_id"] for r in rows]
        refunds = self._rows_by_ids("refund_order", "order_id", order_ids)
        comments = self._rows_by_ids("comment_master", "order_id", order_ids)
        discounts = [float(r["discount_amount"]) for r in rows]
        pays = [float(r["pay_amount"]) for r in rows]
        refund_rate = len(refunds) / max(1, len(rows))
        comment_rate = len(comments) / max(1, len(rows))
        discount_ratio = sum(discounts) / max(1.0, sum(discounts) + sum(pays))
        composite = max(0.04, refund_rate * 0.45 + discount_ratio * 0.35 + comment_rate * 0.20)
        return {"refund_rate": refund_rate, "comment_rate": comment_rate, "discount_ratio": discount_ratio, "composite_risk": composite}

    def _upsert_case(self, case: dict[str, Any]) -> None:
        self.con.execute(
            """
            INSERT OR REPLACE INTO risk_case
            (case_id, pattern_id, pattern_name, risk_level, risk_score, assertion, status, created_at,
             primary_entities, scores, signal_strength, evidence_requirements, next_actions)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                case["case_id"],
                case["pattern_id"],
                case["pattern_name"],
                case["risk_level"],
                case["risk_score"],
                case["assertion"],
                case["status"],
                case["created_at"],
                jdump(case["primary_entities"]),
                jdump(case["scores"]),
                jdump(case["signal_strength"]),
                jdump(case["evidence_requirements"]),
                jdump(case["next_actions"]),
            ),
        )

    def get_case(self, case_id: str) -> dict[str, Any]:
        row = self.con.execute("SELECT * FROM risk_case WHERE case_id=?", (case_id,)).fetchone()
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

    def build_case_graph(self, case_id: str) -> nx.Graph:
        case = self.get_case(case_id)
        entities = case["primary_entities"]
        g = nx.Graph(case_id=case_id)

        assertion_id = f"{case_id}:assertion"
        g.add_node(case_id, type="case", label=case_id, risk_score=case["risk_score"])
        g.add_node(assertion_id, type="assertion", label=case["pattern_id"], text=case["assertion"])
        g.add_edge(case_id, assertion_id, relation="has_assertion", weight=1.0)

        for oid in entities.get("orders", []):
            g.add_node(oid, type="order", label=oid)
            g.add_edge(case_id, oid, relation="contains", weight=0.4)

        for row in self._rows_by_ids("order_master", "order_id", entities.get("orders", [])):
            for node, kind in [
                (row["user_id"], "user"),
                (row["device_id"], "device"),
                (row["ip_address"], "ip"),
                (row["merchant_id"], "merchant"),
            ]:
                g.add_node(node, type=kind, label=node)
            g.add_edge(row["order_id"], row["user_id"], relation="placed_by", weight=0.55)
            g.add_edge(row["order_id"], row["device_id"], relation="used_device", weight=0.78)
            g.add_edge(row["order_id"], row["ip_address"], relation="from_ip", weight=0.72)
            g.add_edge(row["order_id"], row["merchant_id"], relation="sold_by", weight=0.45)

        for row in self._rows_by_ids("payment_record", "order_id", entities.get("orders", [])):
            pay = row["payment_account_hash"]
            g.add_node(pay, type="payment_account", label=pay)
            g.add_edge(row["order_id"], pay, relation="paid_by", weight=0.76)

        for row in self._rows_by_ids("refund_order", "order_id", entities.get("orders", [])):
            rid = row["refund_id"]
            g.add_node(rid, type="refund", label=rid)
            g.add_edge(row["order_id"], rid, relation="refunded", weight=0.7)

        for row in self._rows_by_ids("logistics_order", "order_id", entities.get("orders", [])):
            lid = row["logistics_id"]
            addr = row["receiver_address"]
            g.add_node(lid, type="logistics", label=lid, quality=row["track_quality_score"])
            g.add_node(addr, type="address", label=addr)
            g.add_edge(row["order_id"], lid, relation="shipped_by", weight=0.52)
            g.add_edge(lid, addr, relation="delivered_to", weight=0.5)

        for row in self.con.execute("SELECT * FROM evidence WHERE case_id=?", (case_id,)).fetchall():
            ev_id = row["evidence_id"]
            relation = "supports" if row["kind"] == "support" else "contradicts" if row["kind"] == "counter" else "qualifies"
            g.add_node(ev_id, type="evidence", label=row["dimension"], kind=row["kind"], confidence=row["confidence"])
            g.add_edge(ev_id, assertion_id, relation=relation, weight=float(row["confidence"]))

        return g

    def graph_json(self, case_id: str) -> dict[str, Any]:
        g = self.build_case_graph(case_id)
        nodes = [
            {
                "id": n,
                "label": data.get("label", n),
                "type": data.get("type", "entity"),
                **{k: v for k, v in data.items() if k not in {"label", "type"}},
            }
            for n, data in g.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, "relation": data.get("relation", "related"), "weight": data.get("weight", 0.5)}
            for u, v, data in g.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges, "metrics": {"nodes": len(nodes), "edges": len(edges)}}

    def _rows_by_ids(self, table: str, id_col: str, ids: list[str]):
        if not ids:
            return []
        placeholders = ",".join(["?"] * len(ids))
        return self.con.execute(f"SELECT * FROM {table} WHERE {id_col} IN ({placeholders})", ids).fetchall()
