"""Batch evaluation: run all 500 payments through the loop and print a report.

Usage:
  python evaluate.py                # uses LLM if OPENAI_API_KEY set, else fallback
  python evaluate.py --no-llm       # force deterministic fallback
  python evaluate.py --limit 50     # subset (handy while testing the LLM path)
  python evaluate.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import database as db  # noqa: E402
import dataset  # noqa: E402
import metrics  # noqa: E402
from orchestrator import run_case  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--json")
    a = ap.parse_args()

    db.init_db()
    if db.count_payments() == 0:
        db.upsert_payments(dataset.generate())
    db.reset_cases()
    ids = [p["payment_id"] for p in db.list_payments()]
    if a.limit:
        ids = ids[: a.limit]
    use_llm = False if a.no_llm else None

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, _ in enumerate(ex.map(lambda pid: run_case(pid, use_llm=use_llm), ids), 1):
            if i % 50 == 0:
                print(f"  {i}/{len(ids)}", file=sys.stderr)
    dt = time.time() - t0

    m = metrics.compute()
    print("\n=== RecoverAI evaluation ===")
    print(f"Processed              {m['processed']} payments in {dt:.1f}s "
          f"(LLM: {m['llm_decisions']}, fallback: {m['fallback_decisions']})")
    print(f"At risk                ₹{m['at_risk_amount']:,.0f}")
    print(f"Recovered              ₹{m['recovered_amount']:,.0f}  ({m['recovered_count']} payments)")
    print(f"Escalated to humans    {m['escalated_count']}  (₹{m['escalated_amount']:,.0f})")
    print(f"Unresolved             {m['unresolved_count']}")
    print(f"Unrecoverable          {m['unrecoverable_count']}")
    print(f"Recovery rate          {m['recovery_rate']:.1f}%  (recovered / {m['recoverable_count']} recoverable)")
    print(f"Attempt success rate   {m['attempt_success_rate']:.1f}%  (recovered / {m['auto_handled']} automated attempts)")
    print(f"Decision accuracy      {m['decision_accuracy']:.1f}%  (final action vs ground truth)")
    print(f"Raw LLM accuracy       {m['llm_raw_accuracy']:.1f}%  (before policy gate)")
    print(f"Policy overrides       {m['policy_overrides']}  {m['policy_override_breakdown']}")
    print("\nFinal actions:", m["final_action_counts"])
    print("\nBy failure reason:")
    for r, v in sorted(m["by_failure_reason"].items(), key=lambda kv: -kv[1]["at_risk"]):
        print(f"  {r:<22} {v['recovered']:>3}/{v['count']:<3}  ₹{v['amount_recovered']:>10,.0f}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(m, f, indent=2)
        print(f"\nwrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
