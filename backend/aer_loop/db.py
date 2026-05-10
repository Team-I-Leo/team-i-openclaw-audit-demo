from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import ensure_runtime_dirs, settings


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_runtime_dirs()
    con = sqlite3.connect(db_path or settings.db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    con = connect(db_path)
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def jload(value: str | bytes | None, default: Any = None) -> Any:
    if value is None:
        return default
    return json.loads(value)


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_account (
          user_id TEXT PRIMARY KEY,
          register_time TEXT,
          register_ip TEXT,
          register_device_id TEXT,
          account_status TEXT,
          history_order_count INTEGER,
          history_gmv REAL,
          behavior_richness_score REAL,
          student_cert_status TEXT
        );

        CREATE TABLE IF NOT EXISTS merchant_account (
          merchant_id TEXT PRIMARY KEY,
          merchant_level TEXT,
          created_at TEXT,
          category_id TEXT,
          warehouse_region TEXT
        );

        CREATE TABLE IF NOT EXISTS device_fingerprint (
          device_id TEXT PRIMARY KEY,
          is_emulator INTEGER,
          is_rooted INTEGER,
          multi_user_flag INTEGER,
          screen_resolution TEXT,
          os_type TEXT
        );

        CREATE TABLE IF NOT EXISTS ip_profile (
          ip_address TEXT PRIMARY KEY,
          ip_segment TEXT,
          geo_country TEXT,
          geo_city TEXT,
          is_proxy INTEGER,
          is_datacenter INTEGER,
          ip_type TEXT
        );

        CREATE TABLE IF NOT EXISTS order_master (
          order_id TEXT PRIMARY KEY,
          user_id TEXT,
          merchant_id TEXT,
          sku_id TEXT,
          category_id TEXT,
          order_amount REAL,
          pay_amount REAL,
          discount_amount REAL,
          coupon_id TEXT,
          coupon_type TEXT,
          order_time TEXT,
          pay_time TEXT,
          confirm_time TEXT,
          order_status TEXT,
          device_id TEXT,
          ip_address TEXT,
          is_promo_period INTEGER,
          promo_event_id TEXT,
          promo_intensity TEXT,
          fraud_type TEXT
        );

        CREATE TABLE IF NOT EXISTS payment_record (
          payment_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          payment_tool TEXT,
          payment_account_hash TEXT,
          payment_time TEXT,
          payment_status TEXT,
          card_bin TEXT
        );

        CREATE TABLE IF NOT EXISTS refund_order (
          refund_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          refund_amount REAL,
          refund_reason TEXT,
          apply_time TEXT,
          complete_time TEXT,
          refund_path TEXT
        );

        CREATE TABLE IF NOT EXISTS logistics_order (
          logistics_id TEXT PRIMARY KEY,
          order_id TEXT,
          carrier_code TEXT,
          carrier_name TEXT,
          ship_time TEXT,
          receive_time TEXT,
          receive_type TEXT,
          sender_address TEXT,
          receiver_address TEXT,
          logistics_cost REAL,
          track_quality_score REAL
        );

        CREATE TABLE IF NOT EXISTS logistics_track (
          track_id TEXT PRIMARY KEY,
          logistics_id TEXT,
          order_id TEXT,
          scan_time TEXT,
          scan_type TEXT,
          location TEXT,
          operator_code TEXT,
          raw_payload TEXT
        );

        CREATE TABLE IF NOT EXISTS comment_master (
          comment_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          rating INTEGER,
          comment_time TEXT,
          comment_text TEXT,
          text_length INTEGER,
          sentiment_score REAL,
          image_hash TEXT
        );

        CREATE TABLE IF NOT EXISTS subsidy_record (
          subsidy_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          promo_event_id TEXT,
          subsidy_type TEXT,
          subsidy_amount REAL,
          funded_by TEXT,
          eligibility_key TEXT,
          claimed_at TEXT,
          rule_version TEXT,
          abuse_signal TEXT
        );

        CREATE TABLE IF NOT EXISTS external_ieee_transaction (
          transaction_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          card_hash TEXT,
          addr_hash TEXT,
          device_hash TEXT,
          transaction_amt REAL,
          dist1 REAL,
          c1 REAL,
          c13 REAL,
          fraud_label INTEGER,
          source_file TEXT
        );

        CREATE TABLE IF NOT EXISTS gateway_log (
          event_id TEXT PRIMARY KEY,
          order_id TEXT,
          user_id TEXT,
          device_id TEXT,
          ip_address TEXT,
          event_time TEXT,
          endpoint TEXT,
          latency_ms INTEGER,
          risk_hint TEXT,
          raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS device_log (
          event_id TEXT PRIMARY KEY,
          device_id TEXT,
          user_id TEXT,
          event_time TEXT,
          event_type TEXT,
          os_signal TEXT,
          automation_score REAL,
          raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_event (
          event_id TEXT PRIMARY KEY,
          source_system TEXT,
          source_table TEXT,
          entity_type TEXT,
          entity_id TEXT,
          event_time TEXT,
          case_hint TEXT,
          payload TEXT
        );

        CREATE TABLE IF NOT EXISTS risk_pattern (
          pattern_id TEXT PRIMARY KEY,
          pattern_name TEXT,
          version TEXT,
          status TEXT,
          definition TEXT
        );

        CREATE TABLE IF NOT EXISTS risk_case (
          case_id TEXT PRIMARY KEY,
          pattern_id TEXT,
          pattern_name TEXT,
          risk_level TEXT,
          risk_score REAL,
          assertion TEXT,
          status TEXT,
          created_at TEXT,
          primary_entities TEXT,
          scores TEXT,
          signal_strength TEXT,
          evidence_requirements TEXT,
          next_actions TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence (
          evidence_id TEXT PRIMARY KEY,
          case_id TEXT,
          kind TEXT,
          dimension TEXT,
          description TEXT,
          source TEXT,
          confidence REAL,
          lineage TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence_graph_node (
          node_id TEXT PRIMARY KEY,
          case_id TEXT,
          node_type TEXT,
          label TEXT,
          properties TEXT
        );

        CREATE TABLE IF NOT EXISTS evidence_graph_edge (
          edge_id TEXT PRIMARY KEY,
          case_id TEXT,
          source_id TEXT,
          target_id TEXT,
          relation TEXT,
          weight REAL,
          properties TEXT
        );

        CREATE TABLE IF NOT EXISTS case_thread (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT,
          thread_step INTEGER,
          agent_id TEXT,
          action_taken TEXT,
          tool_params TEXT,
          observation_summary TEXT,
          support_evidence_delta TEXT,
          counter_evidence_delta TEXT,
          unresolved_conflicts TEXT,
          model_reasoning TEXT,
          policy_version TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS trajectory (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT,
          agent_id TEXT,
          state_json TEXT,
          decision_json TEXT,
          observation_json TEXT,
          reward_json TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS passport (
          case_id TEXT PRIMARY KEY,
          passport_json TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS human_review (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id TEXT,
          decision TEXT,
          note TEXT,
          reviewer TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS candidate_pattern (
          candidate_id TEXT PRIMARY KEY,
          name TEXT,
          supporting_cases TEXT,
          common_signals TEXT,
          required_counter_checks TEXT,
          status TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS case_memory (
          memory_id TEXT PRIMARY KEY,
          pattern_id TEXT,
          title TEXT,
          summary TEXT,
          signals TEXT,
          counter_checks TEXT,
          resolution TEXT,
          created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS policy_action_weight (
          pattern_id TEXT,
          action_name TEXT,
          weight_delta REAL,
          support_count INTEGER,
          source_candidate_id TEXT,
          updated_at TEXT,
          PRIMARY KEY (pattern_id, action_name, source_candidate_id)
        );

        CREATE TABLE IF NOT EXISTS model_invocation (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          agent_id TEXT,
          role TEXT,
          backend TEXT,
          model TEXT,
          used_fallback INTEGER,
          prompt_chars INTEGER,
          response_chars INTEGER,
          created_at TEXT
        );
        """
    )
    _ensure_columns(
        con,
        "risk_case",
        {
            "signal_strength": "TEXT",
            "evidence_requirements": "TEXT",
        },
    )


def _ensure_columns(con: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, spec in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def reset_db(con: sqlite3.Connection) -> None:
    tables = [
        "model_invocation",
        "policy_action_weight",
        "case_memory",
        "candidate_pattern",
        "human_review",
        "passport",
        "trajectory",
        "case_thread",
        "evidence_graph_edge",
        "evidence_graph_node",
        "evidence",
        "risk_case",
        "risk_pattern",
        "audit_event",
        "external_ieee_transaction",
        "device_log",
        "gateway_log",
        "subsidy_record",
        "comment_master",
        "logistics_track",
        "logistics_order",
        "refund_order",
        "payment_record",
        "order_master",
        "ip_profile",
        "device_fingerprint",
        "merchant_account",
        "user_account",
    ]
    for table in tables:
        con.execute(f"DELETE FROM {table}")
