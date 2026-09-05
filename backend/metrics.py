"""Aggregate metrics computed from processed cases."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict

import database as db


def compute() -> Dict[str, Any]:
    payments = db.list_payments()
    cases = db.list_cases()
    total = len(payments)
    at_risk = sum(p["amount"] for p in payments)

    processed = len(cases)
    recovered_cases = [c for c in cases if c["status"] == "RECOVERED"]
    recovered_amount = sum(c["execution"]["amount_recovered"] for c in recovered_cases)
    status_counts = Counter(c["status"] for c in cases)
    final_action_counts = Counter(c["policy"]["final_action"] for c in cases)
    proposed_action_counts = Counter(c["decision"]["recommended_action"] for c in cases)
    gt_recoverable = sum(1 for c in cases if c["payment"]["ground_truth_recoverable"])
    agent_attempted = sum(1 for c in cases if c["policy"]["final_action"] in ("RETRY_PAYMENT", "WAIT_AND_RETRY", "CREATE_PAYMENT_LINK"))
    correct = sum(1 for c in cases if c["decision_correct"])
    llm_correct = sum(1 for c in cases if c["decision"]["recommended_action"] == c["payment"]["ground_truth_action"])
    policy_overrides = sum(1 for c in cases if not c["policy"]["allowed"])
    llm_used = sum(1 for c in cases if c["decision"].get("source") == "llm")

    # Policy override breakdown
    override_pairs = Counter(
        f"{c['decision']['recommended_action']} → {c['policy']['final_action']}" for c in cases if not c["policy"]["allowed"]
    )
    # Per failure reason
    by_reason: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "recovered": 0, "amount_recovered": 0.0, "at_risk": 0.0})
    for c in cases:
        r = c["payment"]["failure_reason"]
        by_reason[r]["count"] += 1
        by_reason[r]["at_risk"] += c["payment"]["amount"]
        if c["status"] == "RECOVERED":
            by_reason[r]["recovered"] += 1
            by_reason[r]["amount_recovered"] += c["execution"]["amount_recovered"]

    # Escalated value (needs human attention)
    escalated_amount = sum(c["payment"]["amount"] for c in cases if c["status"] == "ESCALATED")

    return {
        "total_payments": total,
        "processed": processed,
        "at_risk_amount": at_risk,
        "recovered_amount": recovered_amount,
        "escalated_amount": escalated_amount,
        "recoverable_count": gt_recoverable,
        "auto_handled": agent_attempted,
        "recovered_count": len(recovered_cases),
        "escalated_count": status_counts.get("ESCALATED", 0),
        "unresolved_count": status_counts.get("UNRESOLVED", 0),
        "unrecoverable_count": status_counts.get("UNRECOVERABLE", 0),
        "recovery_rate": (len(recovered_cases) / gt_recoverable * 100) if gt_recoverable else 0.0,
        "attempt_success_rate": (len(recovered_cases) / agent_attempted * 100) if agent_attempted else 0.0,
        "decision_accuracy": (correct / processed * 100) if processed else 0.0,
        "llm_raw_accuracy": (llm_correct / processed * 100) if processed else 0.0,
        "policy_overrides": policy_overrides,
        "policy_override_breakdown": dict(override_pairs),
        "llm_decisions": llm_used,
        "fallback_decisions": processed - llm_used,
        "status_counts": dict(status_counts),
        "final_action_counts": dict(final_action_counts),
        "proposed_action_counts": dict(proposed_action_counts),
        "by_failure_reason": dict(by_reason),
    }
