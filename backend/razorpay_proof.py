"""Prove the action layer against REAL Razorpay test mode.

Creates one Payment Link and one Order via the RazorpayTestMode adapter for
the demo cases, then saves the raw API responses to docs/razorpay_proof.json.
Open https://dashboard.razorpay.com/app/payment-links (test mode toggled ON)
and screenshot the entries for the README.

  RECOVERAI_PROVIDER=razorpay RAZORPAY_KEY_ID=rzp_test_... RAZORPAY_KEY_SECRET=... \
      python razorpay_proof.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import database as db  # noqa: E402
import dataset  # noqa: E402
from actions import RazorpayTestMode  # noqa: E402
from models import Payment  # noqa: E402


def main() -> int:
    if not os.environ.get("RAZORPAY_KEY_ID", "").startswith("rzp_test_"):
        print("Set RAZORPAY_KEY_ID=rzp_test_... and RAZORPAY_KEY_SECRET in .env first.", file=sys.stderr)
        return 1
    db.init_db()
    if db.count_payments() == 0:
        db.upsert_payments(dataset.generate())
    prov = RazorpayTestMode()
    proof = {"generated_at": datetime.now(timezone.utc).isoformat(), "key_id": os.environ["RAZORPAY_KEY_ID"][:12] + "…", "calls": []}

    for pid, kind in (("P0003", "payment_link"), ("P0042", "retry")):
        p = Payment(**db.get_payment(pid))
        res = prov.payment_link(p) if kind == "payment_link" else prov.retry(p)
        print(f"{pid}: {kind:<13} → {res.reference}   {res.detail}")
        proof["calls"].append({"payment_id": pid, "kind": kind, "amount": p.amount, "razorpay_id": res.reference, "detail": res.detail})

    out = os.path.join(os.path.dirname(__file__), "..", "docs", "razorpay_proof.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(proof, f, indent=2)
    print(f"\nwrote {out}\nNow screenshot the Razorpay test dashboard → docs/razorpay_dashboard.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
