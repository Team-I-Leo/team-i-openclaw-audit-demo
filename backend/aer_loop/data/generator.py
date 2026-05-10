from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from ..config import settings
from ..db import init_db, jdump, reset_db


BASE_TIME = datetime(2025, 11, 27, 0, 0, 0)


def _ts(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _insert_many(con, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})"
    con.executemany(sql, [[row.get(col) for col in cols] for row in rows])


def _load_patterns(con) -> None:
    pattern_dir = settings.project_root / "data" / "patterns"
    for path in sorted(pattern_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        con.execute(
            "INSERT OR REPLACE INTO risk_pattern VALUES (?,?,?,?,?)",
            (
                data["pattern_id"],
                data["pattern_name"],
                data.get("version", "v1"),
                data.get("status", "active"),
                jdump(data),
            ),
        )


def generate_demo_data(con, order_count: int | None = None, reset: bool = True) -> dict:
    """Seed a multi-source cross-border ecommerce audit demo.

    The seeded dataset intentionally contains three risk patterns from the
    final route-calibration documents:
    EC-SKIM-001, EC-FAKE-002, and EC-ARBI-003. Each case is represented across
    business tables, uploaded gateway/device logs, subsidy ledger, logistics
    traces, and an IEEE-CIS-style external feature table.
    """

    init_db(con)
    if reset:
        reset_db(con)

    random.seed(settings.seed)
    order_count = order_count or settings.demo_order_count

    users: list[dict] = []
    devices: list[dict] = []
    ips: list[dict] = []
    merchants: list[dict] = []

    device_count = max(1400, order_count // 10)
    user_count = max(3000, order_count // 4)
    ip_count = 420
    merchant_count = 220

    for i in range(device_count):
        devices.append(
            {
                "device_id": f"D{i:05d}",
                "is_emulator": 1 if random.random() < 0.04 else 0,
                "is_rooted": 1 if random.random() < 0.03 else 0,
                "multi_user_flag": 1 if random.random() < 0.08 else 0,
                "screen_resolution": random.choice(["1170x2532", "1080x2400", "1440x3200", "1920x1080"]),
                "os_type": random.choice(["ios", "android", "android", "android"]),
            }
        )

    for i in range(ip_count):
        seg = f"10.{i // 254}.{i % 254}"
        ip_type = random.choices(
            ["home_broadband", "mobile", "campus", "corporate", "datacenter"],
            weights=[44, 30, 8, 12, 6],
        )[0]
        ips.append(
            {
                "ip_address": f"{seg}.{random.randint(1, 250)}",
                "ip_segment": seg,
                "geo_country": random.choice(["US", "US", "US", "CA", "GB"]),
                "geo_city": random.choice(["Los Angeles", "New York", "Chicago", "Seattle", "Toronto"]),
                "is_proxy": 1 if ip_type == "datacenter" or random.random() < 0.02 else 0,
                "is_datacenter": 1 if ip_type == "datacenter" else 0,
                "ip_type": ip_type,
            }
        )

    for i in range(user_count):
        reg = BASE_TIME - timedelta(days=random.randint(1, 720), minutes=random.randint(0, 1440))
        ip = random.choice(ips)
        dev = random.choice(devices)
        users.append(
            {
                "user_id": f"U{i:06d}",
                "register_time": _ts(reg),
                "register_ip": ip["ip_address"],
                "register_device_id": dev["device_id"],
                "account_status": "active",
                "history_order_count": random.randint(0, 35),
                "history_gmv": round(random.random() * 1800, 2),
                "behavior_richness_score": round(random.random(), 3),
                "student_cert_status": "verified" if ip["ip_type"] == "campus" and random.random() < 0.45 else "none",
            }
        )

    categories = ["beauty", "electronics", "home", "apparel", "sports"]
    for i in range(merchant_count):
        merchants.append(
            {
                "merchant_id": f"M{i:04d}",
                "merchant_level": random.choice(["new", "bronze", "silver", "gold"]),
                "created_at": _ts(BASE_TIME - timedelta(days=random.randint(1, 1200))),
                "category_id": random.choice(categories),
                "warehouse_region": random.choice(["US-W", "US-E", "US-C", "CA-E"]),
            }
        )

    case_specs = {
        "EC-SKIM-001": {
            "prefix": "SKIM",
            "users": 14,
            "devices": 3,
            "ips": ["172.31.88.11", "172.31.88.12"],
            "merchant": ("M_SKIM", "beauty", "US-W"),
        },
        "EC-FAKE-002": {
            "prefix": "FAKE",
            "users": 24,
            "devices": 4,
            "ips": ["172.31.92.21", "172.31.92.22"],
            "merchant": ("M_FAKE", "electronics", "US-E"),
        },
        "EC-ARBI-003": {
            "prefix": "ARBI",
            "users": 18,
            "devices": 5,
            "ips": ["172.31.99.31", "172.31.99.32", "172.31.99.33"],
            "merchant": ("M_ARBI", "apparel", "US-C"),
        },
    }

    special_entities: dict[str, dict[str, list[str] | str]] = {}
    for pattern_id, spec in case_specs.items():
        prefix = str(spec["prefix"])
        user_ids = [f"U_{prefix}_{i:02d}" for i in range(int(spec["users"]))]
        device_ids = [f"D_{prefix}_{i:02d}" for i in range(int(spec["devices"]))]
        ip_values = list(spec["ips"])
        merchant_id, category, warehouse = spec["merchant"]
        special_entities[pattern_id] = {
            "users": user_ids,
            "devices": device_ids,
            "ips": ip_values,
            "merchant": merchant_id,
        }
        for i, did in enumerate(device_ids):
            devices.append(
                {
                    "device_id": did,
                    "is_emulator": 1,
                    "is_rooted": 1 if i % 2 == 0 else 0,
                    "multi_user_flag": 1,
                    "screen_resolution": "1080x2400",
                    "os_type": "android",
                }
            )
        for ip in ip_values:
            ips.append(
                {
                    "ip_address": ip,
                    "ip_segment": ".".join(ip.split(".")[:3]),
                    "geo_country": "US",
                    "geo_city": "Los Angeles",
                    "is_proxy": 1,
                    "is_datacenter": 1,
                    "ip_type": "datacenter",
                }
            )
        for i, uid in enumerate(user_ids):
            users.append(
                {
                    "user_id": uid,
                    "register_time": _ts(BASE_TIME - timedelta(days=2 + i % 3, minutes=i * 7)),
                    "register_ip": ip_values[i % len(ip_values)],
                    "register_device_id": device_ids[i % len(device_ids)],
                    "account_status": "active",
                    "history_order_count": 0 if pattern_id != "EC-FAKE-002" else random.randint(0, 2),
                    "history_gmv": 0.0,
                    "behavior_richness_score": 0.05 if pattern_id != "EC-FAKE-002" else 0.12,
                    "student_cert_status": "none",
                }
            )
        merchants.append(
            {
                "merchant_id": merchant_id,
                "merchant_level": "silver" if pattern_id == "EC-SKIM-001" else "new",
                "created_at": _ts(BASE_TIME - timedelta(days=400 if pattern_id == "EC-SKIM-001" else 35)),
                "category_id": category,
                "warehouse_region": warehouse,
            }
        )

    _insert_many(con, "device_fingerprint", devices)
    _insert_many(con, "ip_profile", ips)
    _insert_many(con, "user_account", users)
    _insert_many(con, "merchant_account", merchants)

    orders: list[dict] = []
    payments: list[dict] = []
    refunds: list[dict] = []
    logistics: list[dict] = []
    comments: list[dict] = []
    gateway_logs: list[dict] = []
    device_logs: list[dict] = []
    subsidies: list[dict] = []
    ieee: list[dict] = []

    normal_users = [u["user_id"] for u in users if not u["user_id"].startswith("U_")]
    normal_devices = [d["device_id"] for d in devices if not d["device_id"].startswith("D_")]
    normal_ips = [ip["ip_address"] for ip in ips if not ip["ip_address"].startswith("172.31.")]
    merchant_ids = [m["merchant_id"] for m in merchants if not m["merchant_id"].startswith("M_")]

    for i in range(order_count):
        oid = f"O{i:08d}"
        uid = random.choice(normal_users)
        did = random.choice(normal_devices)
        ip = random.choice(normal_ips)
        merchant = random.choice(merchant_ids)
        order_time = BASE_TIME + timedelta(minutes=random.randint(0, 4320))
        amount = round(random.uniform(8, 220), 2)
        promo = random.random() < 0.38
        discount = round(amount * random.choice([0, 0.05, 0.1, 0.2]), 2) if promo else 0.0
        pay = round(amount - discount, 2)
        category = random.choice(categories)
        _append_order_bundle(
            orders,
            payments,
            refunds,
            logistics,
            comments,
            gateway_logs,
            device_logs,
            subsidies,
            ieee,
            oid=oid,
            uid=uid,
            did=did,
            ip=ip,
            merchant=merchant,
            category=category,
            order_time=order_time,
            amount=amount,
            discount=discount,
            pay=pay,
            promo=promo,
            fraud_type="normal",
            payment_account=f"PAY{random.randint(1, 9000):05d}",
            refund_probability=0.06,
            comment_probability=0.42,
            comment_text=random.choice(["Great product", "Fast shipping", "Good value", "As expected"]),
            image_hash=f"IMG{random.randint(1, 10000):05d}" if random.random() < 0.15 else "",
            logistics_quality=round(random.uniform(0.72, 0.99), 3),
            receive_type=random.choice(["signed", "locker", "front_door"]),
            automation_score=random.uniform(0.02, 0.32),
            gateway_hint="none",
            ieee_label=0,
        )

    _inject_skim_case(orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee, special_entities["EC-SKIM-001"])
    _inject_fake_case(orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee, special_entities["EC-FAKE-002"])
    _inject_arbi_case(orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee, special_entities["EC-ARBI-003"])

    _insert_many(con, "order_master", orders)
    _insert_many(con, "payment_record", payments)
    _insert_many(con, "refund_order", refunds)
    _insert_many(con, "logistics_order", logistics)
    _insert_many(con, "comment_master", comments)
    _insert_many(con, "gateway_log", gateway_logs)
    _insert_many(con, "device_log", device_logs)
    _insert_many(con, "subsidy_record", subsidies)
    _insert_many(con, "external_ieee_transaction", ieee)
    _insert_many(con, "logistics_track", _build_logistics_tracks(logistics))

    _materialize_audit_events(con)
    _load_patterns(con)
    _seed_case_memory(con)
    return {
        "orders": len(orders),
        "users": len(users),
        "devices": len(devices),
        "ips": len(ips),
        "payments": len(payments),
        "refunds": len(refunds),
        "logistics": len(logistics),
        "comments": len(comments),
        "gateway_logs": len(gateway_logs),
        "device_logs": len(device_logs),
        "subsidy_records": len(subsidies),
        "ieee_transactions": len(ieee),
        "logistics_tracks": len(logistics) * 3,
    }


def _append_order_bundle(
    orders: list[dict],
    payments: list[dict],
    refunds: list[dict],
    logistics: list[dict],
    comments: list[dict],
    gateway_logs: list[dict],
    device_logs: list[dict],
    subsidies: list[dict],
    ieee: list[dict],
    *,
    oid: str,
    uid: str,
    did: str,
    ip: str,
    merchant: str,
    category: str,
    order_time: datetime,
    amount: float,
    discount: float,
    pay: float,
    promo: bool,
    fraud_type: str,
    payment_account: str,
    refund_probability: float,
    comment_probability: float,
    comment_text: str,
    image_hash: str,
    logistics_quality: float,
    receive_type: str,
    automation_score: float,
    gateway_hint: str,
    ieee_label: int,
) -> None:
    orders.append(
        {
            "order_id": oid,
            "user_id": uid,
            "merchant_id": merchant,
            "sku_id": f"SKU{random.randint(1, 1200):04d}",
            "category_id": category,
            "order_amount": amount,
            "pay_amount": pay,
            "discount_amount": discount,
            "coupon_id": "BF-NEWBIE-18" if discount > 10 else (f"C{random.randint(1, 90):03d}" if discount else ""),
            "coupon_type": "newbie_subsidy" if discount > 10 else ("promo" if promo and discount else "none"),
            "order_time": _ts(order_time),
            "pay_time": _ts(order_time + timedelta(minutes=random.randint(1, 20))),
            "confirm_time": _ts(order_time + timedelta(days=random.randint(2, 9))),
            "order_status": "paid",
            "device_id": did,
            "ip_address": ip,
            "is_promo_period": 1 if promo else 0,
            "promo_event_id": "BF-2025" if promo else "",
            "promo_intensity": "high" if discount > 10 else (random.choice(["low", "medium", "high"]) if promo else "none"),
            "fraud_type": fraud_type,
        }
    )
    payments.append(
        {
            "payment_id": f"P-{oid}",
            "order_id": oid,
            "user_id": uid,
            "payment_tool": random.choice(["card", "paypal", "wallet", "bnpl"]),
            "payment_account_hash": payment_account,
            "payment_time": _ts(order_time + timedelta(minutes=2)),
            "payment_status": "success",
            "card_bin": str(random.randint(400000, 499999)),
        }
    )
    if random.random() < refund_probability:
        refunds.append(
            {
                "refund_id": f"R-{oid}",
                "order_id": oid,
                "user_id": uid,
                "refund_amount": pay,
                "refund_reason": random.choice(["quality", "changed_mind", "late_delivery", "subsidy_arbitrage"]),
                "apply_time": _ts(order_time + timedelta(hours=random.randint(5, 34))),
                "complete_time": _ts(order_time + timedelta(hours=random.randint(12, 48))),
                "refund_path": "original",
            }
        )
    logistics.append(
        {
            "logistics_id": f"L-{oid}",
            "order_id": oid,
            "carrier_code": random.choice(["UPS", "DHL", "FEDEX", "USPS"]),
            "carrier_name": random.choice(["UPS", "DHL", "FedEx", "USPS"]),
            "ship_time": _ts(order_time + timedelta(hours=random.randint(8, 72))),
            "receive_time": _ts(order_time + timedelta(days=random.randint(2, 9))),
            "receive_type": receive_type,
            "sender_address": random.choice(["LA-WH-01", "NY-WH-03", "SEA-WH-02"]),
            "receiver_address": f"ADDR{abs(hash((uid, oid))) % 18000:05d}",
            "logistics_cost": round(random.uniform(0.4, 1.4), 2) if logistics_quality < 0.55 else round(random.uniform(2.5, 14), 2),
            "track_quality_score": logistics_quality,
        }
    )
    if random.random() < comment_probability:
        comments.append(
            {
                "comment_id": f"CMT-{oid}",
                "order_id": oid,
                "user_id": uid,
                "rating": 5 if fraud_type != "normal" else random.choice([4, 5, 5, 5]),
                "comment_time": _ts(order_time + timedelta(days=random.randint(2, 10))),
                "comment_text": comment_text,
                "text_length": len(comment_text),
                "sentiment_score": round(random.uniform(0.88, 0.98), 3) if fraud_type != "normal" else round(random.uniform(0.65, 0.98), 3),
                "image_hash": image_hash,
            }
        )
    if discount > 0:
        subsidies.append(
            {
                "subsidy_id": f"S-{oid}",
                "order_id": oid,
                "user_id": uid,
                "promo_event_id": "BF-2025",
                "subsidy_type": "new_user_coupon" if discount > 10 else "campaign_coupon",
                "subsidy_amount": discount,
                "funded_by": "platform",
                "eligibility_key": f"{uid}:{did}:{ip}" if fraud_type == "normal" else f"{did}:{ip}",
                "claimed_at": _ts(order_time + timedelta(minutes=1)),
                "rule_version": "promo_rule_2025_bf_v3",
                "abuse_signal": fraud_type if fraud_type != "normal" else "",
            }
        )
    gateway_logs.append(
        {
            "event_id": f"GW-{oid}",
            "order_id": oid,
            "user_id": uid,
            "device_id": did,
            "ip_address": ip,
            "event_time": _ts(order_time + timedelta(seconds=random.randint(1, 120))),
            "endpoint": "/payment/authorize",
            "latency_ms": random.randint(20, 120) if fraud_type != "normal" else random.randint(40, 900),
            "risk_hint": gateway_hint,
            "raw_json": json.dumps({"ua": "mobile", "retry": random.randint(0, 3), "case_hint": fraud_type if fraud_type != "normal" else ""}),
        }
    )
    if fraud_type != "normal" or random.random() < 0.02:
        device_logs.append(
            {
                "event_id": f"DL-{oid}",
                "device_id": did,
                "user_id": uid,
                "event_time": _ts(order_time - timedelta(minutes=random.randint(1, 8))),
                "event_type": "login",
                "os_signal": "emulator" if automation_score > 0.65 else "normal",
                "automation_score": round(automation_score, 3),
                "raw_json": json.dumps({"rapid_switch": automation_score > 0.65, "case_hint": fraud_type if fraud_type != "normal" else ""}),
            }
        )
    ieee.append(
        {
            "transaction_id": f"IEEE-{oid}",
            "order_id": oid,
            "user_id": uid,
            "card_hash": payment_account,
            "addr_hash": f"ADDRHASH{abs(hash((uid, ip))) % 5000:04d}",
            "device_hash": did,
            "transaction_amt": pay,
            "dist1": round(random.uniform(1, 25) if fraud_type == "normal" else random.uniform(80, 240), 3),
            "c1": round(random.uniform(0, 4) if fraud_type == "normal" else random.uniform(8, 28), 3),
            "c13": round(random.uniform(0, 5) if fraud_type == "normal" else random.uniform(20, 60), 3),
            "fraud_label": ieee_label,
            "source_file": "IEEE-CIS-demo-feature-slice.csv",
        }
    )


def _inject_skim_case(*collections) -> None:
    *collections, entities = collections
    orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee = collections
    users = list(entities["users"])
    devices = list(entities["devices"])
    ips = list(entities["ips"])
    merchant = str(entities["merchant"])
    pay_accounts = [f"PAY_SKIM_{i:02d}" for i in range(4)]
    for i in range(80):
        order_time = BASE_TIME + timedelta(days=1, hours=2, minutes=i)
        amount = round(random.uniform(58, 68), 2)
        _append_order_bundle(
            orders,
            payments,
            refunds,
            logistics,
            comments,
            gateway_logs,
            device_logs,
            subsidies,
            ieee,
            oid=f"O_SKIM_{i:04d}",
            uid=users[i % len(users)],
            did=devices[i % len(devices)],
            ip=ips[i % len(ips)],
            merchant=merchant,
            category="beauty",
            order_time=order_time,
            amount=amount,
            discount=18.0,
            pay=round(amount - 18.0, 2),
            promo=True,
            fraud_type="EC-SKIM-001",
            payment_account=pay_accounts[i % len(pay_accounts)],
            refund_probability=0.76,
            comment_probability=1.0,
            comment_text=random.choice(["Good item", "Nice product", "Fast and good"]),
            image_hash=f"IMG_SKIM_{i % 4}",
            logistics_quality=round(random.uniform(0.15, 0.45), 3),
            receive_type="auto_confirm",
            automation_score=random.uniform(0.74, 0.96),
            gateway_hint="shared_infra",
            ieee_label=1,
        )


def _inject_fake_case(*collections) -> None:
    *collections, entities = collections
    orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee = collections
    users = list(entities["users"])
    devices = list(entities["devices"])
    ips = list(entities["ips"])
    merchant = str(entities["merchant"])
    pay_accounts = [f"PAY_FAKE_{i:02d}" for i in range(7)]
    review_texts = ["Perfect quality, will buy again", "Great value, five stars", "Excellent product and fast shipping"]
    for i in range(64):
        order_time = BASE_TIME + timedelta(days=2, hours=1, minutes=i * 2)
        amount = round(random.uniform(19, 46), 2)
        _append_order_bundle(
            orders,
            payments,
            refunds,
            logistics,
            comments,
            gateway_logs,
            device_logs,
            subsidies,
            ieee,
            oid=f"O_FAKE_{i:04d}",
            uid=users[i % len(users)],
            did=devices[i % len(devices)],
            ip=ips[i % len(ips)],
            merchant=merchant,
            category="electronics",
            order_time=order_time,
            amount=amount,
            discount=round(amount * 0.08, 2),
            pay=round(amount * 0.92, 2),
            promo=True,
            fraud_type="EC-FAKE-002",
            payment_account=pay_accounts[i % len(pay_accounts)],
            refund_probability=0.02,
            comment_probability=1.0,
            comment_text=review_texts[i % len(review_texts)],
            image_hash=f"IMG_FAKE_{i % 5}",
            logistics_quality=round(random.uniform(0.52, 0.78), 3),
            receive_type="front_door" if i % 3 else "auto_confirm",
            automation_score=random.uniform(0.66, 0.91),
            gateway_hint="review_farm",
            ieee_label=1,
        )


def _inject_arbi_case(*collections) -> None:
    *collections, entities = collections
    orders, payments, refunds, logistics, comments, gateway_logs, device_logs, subsidies, ieee = collections
    users = list(entities["users"])
    devices = list(entities["devices"])
    ips = list(entities["ips"])
    merchant = str(entities["merchant"])
    pay_accounts = [f"PAY_ARBI_{i:02d}" for i in range(3)]
    for i in range(72):
        order_time = BASE_TIME + timedelta(days=1, hours=9, minutes=i * 3)
        amount = round(random.uniform(80, 120), 2)
        discount = round(amount * random.uniform(0.35, 0.48), 2)
        _append_order_bundle(
            orders,
            payments,
            refunds,
            logistics,
            comments,
            gateway_logs,
            device_logs,
            subsidies,
            ieee,
            oid=f"O_ARBI_{i:04d}",
            uid=users[i % len(users)],
            did=devices[i % len(devices)],
            ip=ips[i % len(ips)],
            merchant=merchant,
            category="apparel",
            order_time=order_time,
            amount=amount,
            discount=discount,
            pay=round(amount - discount, 2),
            promo=True,
            fraud_type="EC-ARBI-003",
            payment_account=pay_accounts[i % len(pay_accounts)],
            refund_probability=0.38,
            comment_probability=0.2,
            comment_text="As expected",
            image_hash="",
            logistics_quality=round(random.uniform(0.32, 0.62), 3),
            receive_type="locker" if i % 4 else "auto_confirm",
            automation_score=random.uniform(0.58, 0.88),
            gateway_hint="subsidy_arbitrage",
            ieee_label=1,
        )


def _build_logistics_tracks(logistics: list[dict]) -> list[dict]:
    tracks: list[dict] = []
    for row in logistics:
        ship = datetime.fromisoformat(row["ship_time"])
        quality = float(row["track_quality_score"])
        locations = ["origin_hub", "linehaul", "destination_hub"] if quality > 0.55 else ["origin_hub", "synthetic_scan", "auto_receive"]
        for idx, loc in enumerate(locations):
            tracks.append(
                {
                    "track_id": f"TRK-{row['logistics_id']}-{idx}",
                    "logistics_id": row["logistics_id"],
                    "order_id": row["order_id"],
                    "scan_time": _ts(ship + timedelta(hours=idx * 12)),
                    "scan_type": "scan" if loc != "auto_receive" else "auto_confirm",
                    "location": loc,
                    "operator_code": "SYS" if quality < 0.55 else f"OP{idx}",
                    "raw_payload": json.dumps({"quality": quality, "loc": loc}),
                }
            )
    return tracks


def _materialize_audit_events(con) -> None:
    specs = [
        ("order_master", "business_core", "order", "order_id", "order_time"),
        ("payment_record", "payment_gateway", "payment", "payment_id", "payment_time"),
        ("refund_order", "after_sales", "refund", "refund_id", "apply_time"),
        ("logistics_order", "logistics_partner", "logistics", "logistics_id", "ship_time"),
        ("logistics_track", "logistics_partner", "track", "track_id", "scan_time"),
        ("comment_master", "review_system", "comment", "comment_id", "comment_time"),
        ("subsidy_record", "promo_ledger", "subsidy", "subsidy_id", "claimed_at"),
        ("gateway_log", "uploaded_gateway_log", "gateway", "event_id", "event_time"),
        ("device_log", "uploaded_device_log", "device", "event_id", "event_time"),
        ("external_ieee_transaction", "ieee_cis_public_slice", "external_feature", "transaction_id", None),
    ]
    for table, source_system, entity_type, id_col, time_col in specs:
        rows = con.execute(f"SELECT * FROM {table}").fetchall()
        for idx, row in enumerate(rows):
            row_dict = dict(row)
            hint = row_dict.get("fraud_type") or row_dict.get("risk_hint") or row_dict.get("abuse_signal") or ""
            con.execute(
                "INSERT INTO audit_event VALUES (?,?,?,?,?,?,?,?)",
                (
                    f"AE-{table}-{idx:08d}",
                    source_system,
                    table,
                    entity_type,
                    str(row_dict.get(id_col)),
                    str(row_dict.get(time_col)) if time_col else _ts(BASE_TIME),
                    hint,
                    json.dumps(row_dict, ensure_ascii=False),
                ),
            )


def _seed_case_memory(con) -> None:
    rows = [
        {
            "memory_id": "MEM-SKIM-2025-01",
            "pattern_id": "EC-SKIM-001",
            "title": "Promotion subsidy skimming via shared devices",
            "summary": "Prior Black Friday case: new accounts reused emulator devices, datacenter IPs, wallet accounts, and fast refunds.",
            "signals": ["device_reuse", "ip_cluster", "payment_cluster", "refund_under_24h", "low_quality_logistics"],
            "counter_checks": ["family_shared_device", "campus_cluster", "warehouse_batch_shipping"],
            "resolution": "Confirmed abuse after human review.",
        },
        {
            "memory_id": "MEM-FAKE-2025-02",
            "pattern_id": "EC-FAKE-002",
            "title": "Review farm with verified micro orders",
            "summary": "Prior reputation manipulation case: low-value orders, duplicate review images, high automation score, and few refunds.",
            "signals": ["review_similarity", "image_hash_reuse", "automation_score", "merchant_rating_spike"],
            "counter_checks": ["organic_campaign", "influencer_drop", "family_purchase"],
            "resolution": "Merchant warning and review suppression.",
        },
        {
            "memory_id": "MEM-ARBI-2025-03",
            "pattern_id": "EC-ARBI-003",
            "title": "Coupon arbitrage with concentrated payment accounts",
            "summary": "Prior subsidy arbitrage case: high discount ratio, repeated eligibility keys, payment account reuse, partial refunds.",
            "signals": ["subsidy_abuse", "payment_cluster", "refund_abnormal", "promo_cohort_outlier"],
            "counter_checks": ["legitimate_bulk_order", "warehouse_batch_shipping", "corporate_purchase"],
            "resolution": "Promo rule patched after auditor approval.",
        },
    ]
    for row in rows:
        con.execute(
            "INSERT OR REPLACE INTO case_memory VALUES (?,?,?,?,?,?,?,?)",
            (
                row["memory_id"],
                row["pattern_id"],
                row["title"],
                row["summary"],
                jdump(row["signals"]),
                jdump(row["counter_checks"]),
                row["resolution"],
                _ts(BASE_TIME - timedelta(days=30)),
            ),
        )
