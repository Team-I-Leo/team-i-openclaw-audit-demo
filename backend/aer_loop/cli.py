from __future__ import annotations

import argparse
import json

from .config import settings
from .data import generate_demo_data
from .db import init_db, session
from .fusion import EvidenceFusionEngine
from .orchestrator import AERLoopOrchestrator, run_full_demo


def main() -> None:
    parser = argparse.ArgumentParser(prog="aer-loop")
    sub = parser.add_subparsers(dest="cmd", required=True)

    boot = sub.add_parser("bootstrap")
    boot.add_argument("--orders", type=int, default=None)
    boot.add_argument("--no-reset", action="store_true")

    run = sub.add_parser("run")
    run.add_argument("--orders", type=int, default=None)
    run.add_argument("--max-steps", type=int, default=8)
    run.add_argument("--no-reset", action="store_true")

    case = sub.add_parser("case")
    case.add_argument("case_id")
    case.add_argument("--max-steps", type=int, default=8)

    model_smoke = sub.add_parser("model-smoke")
    model_smoke.add_argument("--orders", type=int, default=1200)
    model_smoke.add_argument("--case-id", default="AER-001")
    model_smoke.add_argument("--max-steps", type=int, default=3)

    sub.add_parser("summary")

    args = parser.parse_args()
    if args.cmd == "bootstrap":
        with session() as con:
            out = AERLoopOrchestrator(con).bootstrap(order_count=args.orders, reset=not args.no_reset)
    elif args.cmd == "run":
        out = run_full_demo(order_count=args.orders, max_steps=args.max_steps, reset=not args.no_reset)
    elif args.cmd == "case":
        with session() as con:
            out = AERLoopOrchestrator(con).run_case(args.case_id, max_steps=args.max_steps)
    elif args.cmd == "model-smoke":
        with session() as con:
            init_db(con)
            stats = generate_demo_data(con, order_count=args.orders, reset=True)
            cases = EvidenceFusionEngine(con).build_candidate_cases()
            result = AERLoopOrchestrator(con).run_case(args.case_id, max_steps=args.max_steps)
            out = {
                "bootstrap": {
                    "data": stats,
                    "cases": [
                        {
                            "case_id": c["case_id"],
                            "pattern_id": c["pattern_id"],
                            "risk_score": c["risk_score"],
                            "risk_level": c["risk_level"],
                        }
                        for c in cases
                    ],
                },
                "case_result": result,
                "summary": _summary(),
            }
    elif args.cmd == "summary":
        out = _summary()
    else:
        raise AssertionError(args.cmd)
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _summary() -> dict:
    with session() as con:
        return {
            "db_path": str(settings.db_path),
            "model_backend": settings.model_backend,
            "model_path": settings.model_path,
            "cases": [dict(r) for r in con.execute("SELECT case_id, pattern_id, risk_level, risk_score, status FROM risk_case").fetchall()],
            "model_invocations": [dict(r) for r in con.execute("SELECT agent_id, backend, model, used_fallback, COUNT(*) count FROM model_invocation GROUP BY agent_id, backend, model, used_fallback ORDER BY agent_id").fetchall()],
            "evidence_count": con.execute("SELECT COUNT(*) c FROM evidence").fetchone()["c"],
            "trajectory_count": con.execute("SELECT COUNT(*) c FROM trajectory").fetchone()["c"],
            "thread_count": con.execute("SELECT COUNT(*) c FROM case_thread").fetchone()["c"],
            "passport_count": con.execute("SELECT COUNT(*) c FROM passport").fetchone()["c"],
        }


if __name__ == "__main__":
    main()
