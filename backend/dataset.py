"""Synthetic failed-payment dataset generator with ground-truth labels.

Ground truth is derived from a hand-written labelling function that encodes
what a careful human operator *should* do. The agent (LLM) never sees these
labels; they are used only for evaluation.
"""
from __future__ import annotations

import csv
import os
import random
from typing import Dict, List

from models import Action, FailureReason

FAILURE_MESSAGES: Dict[FailureReason, List[str]] = {
    FailureReason.BANK_TIMEOUT: ["Issuing bank did not respond in time", "Gateway timeout while contacting issuer"],
    FailureReason.BANK_ERROR: ["Issuer returned a temporary processing error", "Bank system unavailable (5xx)"],
    FailureReason.INSUFFICIENT_FUNDS: ["Insufficient funds in account", "Card declined: insufficient balance"],
    FailureReason.EXPIRED_CARD: ["Card expired", "Saved card has passed its expiry date"],
    FailureReason.AUTH_FAILURE: ["3-D Secure / OTP authentication failed", "Customer did not complete OTP verification"],
    FailureReason.PAYMENT_TIMEOUT: ["Payment session timed out before completion", "Customer session expired at gateway"],
    FailureReason.REPEATED_FAILURE: ["Multiple consecutive failures on this payment", "Card declined repeatedly by issuer"],
    FailureReason.CHECKOUT_ABANDONED: ["Customer left checkout before paying", "Checkout closed at payment step"],
    FailureReason.SUBSCRIPTION_FAILURE: ["Recurring mandate debit failed", "Auto-debit for subscription cycle declined"],
    FailureReason.CARD_BLOCKED: ["Card blocked by issuer", "Do-not-honour response from issuer"],
    FailureReason.SUSPECTED_FRAUD: ["Transaction flagged by risk engine", "Issuer declined: suspected fraud"],
}

# Distribution of failure reasons (weights sum to ~1)
REASON_WEIGHTS = [
    (FailureReason.BANK_TIMEOUT, 0.16),
    (FailureReason.BANK_ERROR, 0.10),
    (FailureReason.INSUFFICIENT_FUNDS, 0.18),
    (FailureReason.EXPIRED_CARD, 0.10),
    (FailureReason.AUTH_FAILURE, 0.10),
    (FailureReason.PAYMENT_TIMEOUT, 0.08),
    (FailureReason.REPEATED_FAILURE, 0.07),
    (FailureReason.CHECKOUT_ABANDONED, 0.07),
    (FailureReason.SUBSCRIPTION_FAILURE, 0.08),
    (FailureReason.CARD_BLOCKED, 0.03),
    (FailureReason.SUSPECTED_FRAUD, 0.03),
]

AUTO_LIMIT = 10000.0  # keep in sync with policy.AUTO_ACTION_AMOUNT_LIMIT


def label(rec: dict) -> Action:
    """Ground-truth labelling: what a careful operator would do."""
    r = FailureReason(rec["failure_reason"])
    amt = rec["amount"]
    sr = rec["customer_success_rate"]
    attempts = rec["attempt_count"]
    prev_rec = rec["previous_recovery_attempts"]

    if rec["payment_already_succeeded"]:
        return Action.MARK_UNRECOVERABLE  # nothing to recover - must not act
    if r in (FailureReason.SUSPECTED_FRAUD, FailureReason.CARD_BLOCKED):
        return Action.ESCALATE_TO_HUMAN
    if amt >= AUTO_LIMIT:
        return Action.ESCALATE_TO_HUMAN
    if attempts >= 2 or prev_rec >= 2:
        # automation budget exhausted
        return Action.ESCALATE_TO_HUMAN if sr >= 0.5 else Action.MARK_UNRECOVERABLE
    if rec["days_since_failure"] > 7 and r in (
        FailureReason.BANK_TIMEOUT, FailureReason.BANK_ERROR, FailureReason.PAYMENT_TIMEOUT,
        FailureReason.INSUFFICIENT_FUNDS, FailureReason.SUBSCRIPTION_FAILURE,
    ):
        return Action.ESCALATE_TO_HUMAN  # too stale for an automated retry
    if r in (FailureReason.BANK_TIMEOUT, FailureReason.BANK_ERROR, FailureReason.PAYMENT_TIMEOUT):
        return Action.RETRY_PAYMENT if sr >= 0.6 else Action.CREATE_PAYMENT_LINK
    if r == FailureReason.INSUFFICIENT_FUNDS:
        return Action.WAIT_AND_RETRY if sr >= 0.5 else Action.CREATE_PAYMENT_LINK
    if r in (FailureReason.EXPIRED_CARD, FailureReason.AUTH_FAILURE, FailureReason.CHECKOUT_ABANDONED):
        return Action.CREATE_PAYMENT_LINK
    if r == FailureReason.SUBSCRIPTION_FAILURE:
        if rec["subscription_status"] == "CANCELLED":
            return Action.MARK_UNRECOVERABLE
        return Action.RETRY_PAYMENT if sr >= 0.7 else Action.CREATE_PAYMENT_LINK
    if r == FailureReason.REPEATED_FAILURE:
        return Action.ESCALATE_TO_HUMAN if sr >= 0.5 else Action.MARK_UNRECOVERABLE
    return Action.ESCALATE_TO_HUMAN


def simulate_outcome(rec: dict, rng: random.Random) -> str:
    """Pre-roll the world's response so evaluation is reproducible.

    The simulated outcome represents what happens if the *correct* recovery
    action is taken. Retry success is strongly driven by failure type and
    customer history; payment links depend on customer engagement.
    """
    r = FailureReason(rec["failure_reason"])
    sr = rec["customer_success_rate"]
    gt = rec["ground_truth_action"]
    if gt in (Action.ESCALATE_TO_HUMAN, Action.MARK_UNRECOVERABLE):
        return "N/A"
    base = {
        FailureReason.BANK_TIMEOUT: 0.82,
        FailureReason.BANK_ERROR: 0.78,
        FailureReason.PAYMENT_TIMEOUT: 0.70,
        FailureReason.INSUFFICIENT_FUNDS: 0.55,
        FailureReason.EXPIRED_CARD: 0.60,
        FailureReason.AUTH_FAILURE: 0.58,
        FailureReason.CHECKOUT_ABANDONED: 0.35,
        FailureReason.SUBSCRIPTION_FAILURE: 0.68,
        FailureReason.REPEATED_FAILURE: 0.30,
    }.get(r, 0.4)
    p = base * (0.6 + 0.4 * sr)
    if gt == Action.CREATE_PAYMENT_LINK:
        p *= 0.85
        roll = rng.random()
        if roll < p:
            return "SUCCESS"
        return "EXPIRED" if rng.random() < 0.6 else "FAIL"
    return "SUCCESS" if rng.random() < p else "FAIL"


def generate(n: int = 500, seed: int = 42) -> List[dict]:
    rng = random.Random(seed)
    reasons = [r for r, _ in REASON_WEIGHTS]
    weights = [w for _, w in REASON_WEIGHTS]
    records: List[dict] = []
    for i in range(1, n + 1):
        reason = rng.choices(reasons, weights)[0]
        # amount distribution: mostly small, long tail
        bucket = rng.random()
        if bucket < 0.58:
            amount = rng.choice([199, 299, 499, 599, 799, 999, 1299, 1499, 1999])
        elif bucket < 0.88:
            amount = rng.choice([2499, 2999, 3499, 3999, 4999, 5999, 6999, 7999, 8999])
        else:
            amount = rng.choice([9999, 11999, 12999, 14999, 15999, 19999, 24999, 49999])
        prev_payments = rng.randint(0, 40)
        if prev_payments == 0:
            success_rate = 0.5
        else:
            success_rate = round(min(1.0, max(0.1, rng.gauss(0.85, 0.15))), 2)
        attempt_count = rng.choices([0, 1, 2, 3], [0.66, 0.24, 0.07, 0.03])[0]
        if reason == FailureReason.REPEATED_FAILURE:
            attempt_count = max(attempt_count, 2)
        sub_status = "NONE"
        if reason == FailureReason.SUBSCRIPTION_FAILURE:
            sub_status = rng.choices(["ACTIVE", "PAST_DUE", "CANCELLED"], [0.5, 0.35, 0.15])[0]
        elif rng.random() < 0.25:
            sub_status = rng.choice(["ACTIVE", "PAST_DUE"])
        rec = {
            "payment_id": f"P{i:04d}",
            "customer_id": f"C{rng.randint(1000, 1999)}",
            "amount": float(amount),
            "currency": "INR",
            "failure_reason": reason.value,
            "failure_message": rng.choice(FAILURE_MESSAGES[reason]),
            "attempt_count": attempt_count,
            "customer_success_rate": success_rate,
            "previous_payments": prev_payments,
            "subscription_status": sub_status,
            "days_since_failure": round(rng.choice([0.01, 0.05, 0.2, 0.5, 1, 2, 3, 5, 7]) * rng.uniform(0.8, 1.2), 2),
            "previous_recovery_attempts": rng.choices([0, 1, 2], [0.76, 0.19, 0.05])[0],
            "payment_already_succeeded": rng.random() < 0.02,  # stale events: must never retry
        }
        gt_action = label(rec)
        rec["ground_truth_action"] = gt_action.value
        rec["ground_truth_recoverable"] = gt_action in (
            Action.RETRY_PAYMENT,
            Action.CREATE_PAYMENT_LINK,
            Action.WAIT_AND_RETRY,
        )
        rec["simulated_outcome"] = simulate_outcome(rec, rng)
        rec["status"] = "PENDING"
        records.append(rec)

    _inject_demo_scenarios(records)
    return records


def _inject_demo_scenarios(records: List[dict]) -> None:
    """Pin a few records to the demo script so the story is reproducible."""
    by_id = {r["payment_id"]: r for r in records}

    def pin(pid: str, **kw):
        r = by_id[pid]
        r.update(kw)
        gt = label(r)
        r["ground_truth_action"] = gt.value
        r["ground_truth_recoverable"] = gt in (Action.RETRY_PAYMENT, Action.CREATE_PAYMENT_LINK, Action.WAIT_AND_RETRY)

    # Easy recovery: transient bank timeout, strong history
    pin("P0042", customer_id="C1042", amount=2499.0, failure_reason=FailureReason.BANK_TIMEOUT.value,
        failure_message="Issuing bank did not respond in time", attempt_count=0, customer_success_rate=0.88,
        previous_payments=8, subscription_status="NONE", days_since_failure=0.02, previous_recovery_attempts=0,
        payment_already_succeeded=False, simulated_outcome="SUCCESS")
    # Payment-link recovery: expired card
    pin("P0003", customer_id="C1003", amount=8999.0, failure_reason=FailureReason.EXPIRED_CARD.value,
        failure_message="Saved card has passed its expiry date", attempt_count=1, customer_success_rate=0.82,
        previous_payments=11, subscription_status="ACTIVE", days_since_failure=0.5, previous_recovery_attempts=0,
        payment_already_succeeded=False, simulated_outcome="SUCCESS")
    # Escalation: high value + repeated failures
    pin("P0099", customer_id="C1099", amount=12999.0, failure_reason=FailureReason.REPEATED_FAILURE.value,
        failure_message="Card declined repeatedly by issuer", attempt_count=2, customer_success_rate=0.61,
        previous_payments=13, subscription_status="NONE", days_since_failure=1.0, previous_recovery_attempts=1,
        payment_already_succeeded=False, simulated_outcome="N/A")
    # Failed recovery handled gracefully: retry is right call but bank still fails
    pin("P0117", customer_id="C1117", amount=1999.0, failure_reason=FailureReason.BANK_ERROR.value,
        failure_message="Bank system unavailable (5xx)", attempt_count=1, customer_success_rate=0.79,
        previous_payments=6, subscription_status="NONE", days_since_failure=0.1, previous_recovery_attempts=1,
        payment_already_succeeded=False, simulated_outcome="FAIL")
    # Stale event: payment already succeeded — policy must block any retry
    pin("P0210", customer_id="C1210", amount=999.0, failure_reason=FailureReason.PAYMENT_TIMEOUT.value,
        failure_message="Payment session timed out before completion", attempt_count=0, customer_success_rate=0.95,
        previous_payments=20, subscription_status="NONE", days_since_failure=0.3, previous_recovery_attempts=0,
        payment_already_succeeded=True, simulated_outcome="N/A")


def write_csv(records: List[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols = [k for k in records[0].keys() if k != "status"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            w.writerow({k: r[k] for k in cols})


if __name__ == "__main__":
    recs = generate()
    out = os.path.join(os.path.dirname(__file__), "..", "data", "payments.csv")
    write_csv(recs, out)
    from collections import Counter
    print(f"wrote {len(recs)} records -> {out}")
    print("actions:", Counter(r["ground_truth_action"] for r in recs))
    print("outcomes:", Counter(r["simulated_outcome"] for r in recs))
    print("total at risk: ₹", sum(r["amount"] for r in recs))
