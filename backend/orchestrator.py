"""The RecoverAI loop: Observe → Reason → Policy → Act → Verify → Record."""
from __future__ import annotations

from typing import Optional

import actions
import agent
import database as db
import policy
from models import Action, AgentDecision, CaseResult, CaseStatus, Payment


def _status_from(final_action: Action, outcome: str) -> CaseStatus:
    if final_action == Action.ESCALATE_TO_HUMAN:
        return CaseStatus.ESCALATED
    if final_action == Action.MARK_UNRECOVERABLE:
        return CaseStatus.UNRECOVERABLE
    if outcome == "SUCCESS":
        return CaseStatus.RECOVERED
    return CaseStatus.UNRESOLVED


def run_case(payment_id: str, use_llm: Optional[bool] = None) -> CaseResult:
    raw = db.get_payment(payment_id)
    if raw is None:
        raise KeyError(payment_id)
    p = Payment(**raw)
    audit = db.record_audit_event

    audit(p.payment_id, "EVENT", "Payment failure received",
          {"amount": p.amount, "failure_reason": p.failure_reason.value, "message": p.failure_message})
    audit(p.payment_id, "OBSERVE", "Customer history retrieved",
          {"previous_payments": p.previous_payments, "success_rate": p.customer_success_rate,
           "subscription_status": p.subscription_status, "attempt_count": p.attempt_count,
           "previous_recovery_attempts": p.previous_recovery_attempts})

    # 1. Reason
    decision: AgentDecision = agent.decide(p, use_llm=use_llm)
    audit(p.payment_id, "REASON", f"AI diagnosis completed ({decision.source})",
          {"diagnosis": decision.diagnosis, "recoverable": decision.recoverable, "confidence": decision.confidence})
    audit(p.payment_id, "DECIDE", f"Recovery strategy selected: {decision.recommended_action.value}",
          {"reason": decision.reason, "expected_recovery": decision.expected_recovery})

    # 2. Policy gate
    verdict = policy.evaluate(p, decision)
    if verdict.allowed:
        audit(p.payment_id, "POLICY", "Policy validation passed",
              {"checks": [c.model_dump() for c in verdict.checks]})
    else:
        audit(p.payment_id, "POLICY", f"Policy BLOCKED {decision.recommended_action.value} → {verdict.final_action.value}",
              {"override_reason": verdict.override_reason, "checks": [c.model_dump() for c in verdict.checks]})

    # 3. Act (only the policy's final action is ever executed)
    result = actions.execute(p, verdict.final_action)
    audit(p.payment_id, "ACT", f"{verdict.final_action.value} executed via {result.provider}",
          {"reference": result.reference, "detail": result.detail})

    # 4. Verify
    status = _status_from(verdict.final_action, result.outcome)
    audit(p.payment_id, "VERIFY", f"Payment result received: {result.outcome}", {"status": status.value})
    if status == CaseStatus.RECOVERED:
        audit(p.payment_id, "OUTCOME", f"Payment recovered — ₹{result.amount_recovered:,.0f} added to recovered revenue")
    elif status == CaseStatus.ESCALATED:
        audit(p.payment_id, "OUTCOME", "Human review required")
    elif status == CaseStatus.UNRECOVERABLE:
        audit(p.payment_id, "OUTCOME", "Marked unrecoverable; no further automated action")
    else:
        audit(p.payment_id, "OUTCOME", "Recovery attempt did not succeed; case left unresolved for follow-up")

    # 5. Record
    correct = verdict.final_action.value == p.ground_truth_action.value
    case = CaseResult(payment=p, decision=decision, policy=verdict, execution=result, status=status, decision_correct=correct)
    case.payment.status = status
    db.save_case(p.payment_id, case.model_dump(mode="json"), status.value, result.amount_recovered, correct)
    return case
