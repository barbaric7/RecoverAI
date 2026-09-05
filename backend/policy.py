"""Deterministic policy engine.

The LLM *recommends* an action. This module decides whether that action is
*allowed*. It is intentionally boring: pure functions, hard limits, no ML.

If a check fails, the action is downgraded to the safest permissible
alternative (usually ESCALATE_TO_HUMAN), and the reason is recorded.
"""
from __future__ import annotations

from typing import List

from models import Action, AgentDecision, FailureReason, Payment, PolicyCheck, PolicyVerdict

# ---- Hard limits (would come from merchant config in production) ----
MAX_AUTOMATED_RETRIES = 2          # total automated retries per payment
AUTO_ACTION_AMOUNT_LIMIT = 10000.0  # INR; above this a human must approve
MIN_CONFIDENCE_FOR_AUTOMATION = 0.55
MIN_CUSTOMER_SUCCESS_RATE_FOR_RETRY = 0.40
MAX_DAYS_FOR_AUTO_RETRY = 7.0
HIGH_RISK_REASONS = {FailureReason.SUSPECTED_FRAUD, FailureReason.CARD_BLOCKED}
# Retrying with the same credential is pointless for these
NON_RETRYABLE_REASONS = {FailureReason.EXPIRED_CARD, FailureReason.CARD_BLOCKED, FailureReason.SUSPECTED_FRAUD}

AUTOMATED_ACTIONS = {Action.RETRY_PAYMENT, Action.WAIT_AND_RETRY, Action.CREATE_PAYMENT_LINK}
RETRY_ACTIONS = {Action.RETRY_PAYMENT, Action.WAIT_AND_RETRY}


def evaluate(payment: Payment, decision: AgentDecision) -> PolicyVerdict:
    checks: List[PolicyCheck] = []
    proposed = decision.recommended_action
    final = proposed
    override: str | None = None

    def add(name: str, passed: bool, detail: str) -> bool:
        checks.append(PolicyCheck(name=name, passed=passed, detail=detail))
        return passed

    # ---- Universal stopping rules (apply to every automated action) ----
    already_paid_ok = add(
        "no_prior_success",
        not payment.payment_already_succeeded,
        "Payment has already succeeded — no recovery permitted"
        if payment.payment_already_succeeded
        else "Payment is still in failed state",
    )
    if not already_paid_ok:
        return PolicyVerdict(
            allowed=proposed == Action.MARK_UNRECOVERABLE,
            final_action=Action.MARK_UNRECOVERABLE,
            checks=checks,
            override_reason="Stale failure event: payment already succeeded. Blocking any action to prevent double charge.",
        )

    if proposed in AUTOMATED_ACTIONS:
        ok_amount = add(
            "amount_limit",
            payment.amount < AUTO_ACTION_AMOUNT_LIMIT,
            f"₹{payment.amount:,.0f} {'<' if payment.amount < AUTO_ACTION_AMOUNT_LIMIT else '>='} auto limit ₹{AUTO_ACTION_AMOUNT_LIMIT:,.0f}",
        )
        ok_conf = add(
            "confidence_threshold",
            decision.confidence >= MIN_CONFIDENCE_FOR_AUTOMATION,
            f"Agent confidence {decision.confidence:.0%} vs minimum {MIN_CONFIDENCE_FOR_AUTOMATION:.0%}",
        )
        ok_risk = add(
            "not_high_risk",
            payment.failure_reason not in HIGH_RISK_REASONS,
            f"Failure reason {payment.failure_reason.value} "
            + ("is high-risk; automation prohibited" if payment.failure_reason in HIGH_RISK_REASONS else "is not high-risk"),
        )
        ok_budget = add(
            "recovery_budget",
            payment.previous_recovery_attempts < MAX_AUTOMATED_RETRIES,
            f"{payment.previous_recovery_attempts} previous automated recovery attempt(s); limit {MAX_AUTOMATED_RETRIES}",
        )
        if not (ok_amount and ok_conf and ok_risk and ok_budget):
            final = Action.ESCALATE_TO_HUMAN
            override = "Automated action blocked by policy: " + "; ".join(
                c.detail for c in checks if not c.passed
            )

    if proposed in RETRY_ACTIONS and final == proposed:
        ok_retry_limit = add(
            "retry_limit",
            payment.attempt_count < MAX_AUTOMATED_RETRIES,
            f"{payment.attempt_count} attempt(s) so far; automated retry limit is {MAX_AUTOMATED_RETRIES}",
        )
        ok_retryable = add(
            "retryable_failure_type",
            payment.failure_reason not in NON_RETRYABLE_REASONS,
            f"{payment.failure_reason.value} "
            + ("cannot be fixed by retrying the same credential" if payment.failure_reason in NON_RETRYABLE_REASONS else "may succeed on retry"),
        )
        ok_customer = add(
            "customer_eligible",
            payment.customer_success_rate >= MIN_CUSTOMER_SUCCESS_RATE_FOR_RETRY,
            f"Customer success rate {payment.customer_success_rate:.0%} vs minimum {MIN_CUSTOMER_SUCCESS_RATE_FOR_RETRY:.0%}",
        )
        ok_fresh = add(
            "freshness",
            payment.days_since_failure <= MAX_DAYS_FOR_AUTO_RETRY,
            f"{payment.days_since_failure} day(s) since failure; retry window {MAX_DAYS_FOR_AUTO_RETRY:.0f} days",
        )
        if not ok_retry_limit:
            final = Action.ESCALATE_TO_HUMAN
            override = "Maximum automated retries reached; escalating instead of retrying."
        elif not ok_retryable:
            # Downgrade to a safer, still-automated action
            final = Action.CREATE_PAYMENT_LINK
            override = "Retrying the same credential cannot succeed; downgraded to payment link."
        elif not ok_customer:
            final = Action.CREATE_PAYMENT_LINK
            override = "Weak customer history; downgraded from retry to payment link (customer-initiated)."
        elif not ok_fresh:
            final = Action.ESCALATE_TO_HUMAN
            override = "Failure is too old for automated retry; escalating."

    if proposed == Action.MARK_UNRECOVERABLE:
        # Guard against the agent giving up too easily on valuable, plausible cases
        premature = (
            payment.customer_success_rate >= 0.7
            and payment.attempt_count < MAX_AUTOMATED_RETRIES
            and payment.failure_reason not in HIGH_RISK_REASONS
            and payment.subscription_status != "CANCELLED"
        )
        add(
            "not_premature_giveup",
            not premature,
            "Customer has strong history and budget remains; a human should confirm before writing off"
            if premature
            else "Write-off is consistent with case facts",
        )
        if premature:
            final = Action.ESCALATE_TO_HUMAN
            override = "Agent proposed write-off but case still looks recoverable; routing to human instead."

    if proposed == Action.ESCALATE_TO_HUMAN:
        # Informational: show which automation gates this case would have failed,
        # so reviewers can see the agent was right not to act on its own.
        add("amount_limit", payment.amount < AUTO_ACTION_AMOUNT_LIMIT,
            f"₹{payment.amount:,.0f} {'<' if payment.amount < AUTO_ACTION_AMOUNT_LIMIT else '>='} auto limit ₹{AUTO_ACTION_AMOUNT_LIMIT:,.0f}")
        add("retry_limit", payment.attempt_count < MAX_AUTOMATED_RETRIES,
            f"{payment.attempt_count} attempt(s) so far; automated retry limit is {MAX_AUTOMATED_RETRIES}")
        add("recovery_budget", payment.previous_recovery_attempts < MAX_AUTOMATED_RETRIES,
            f"{payment.previous_recovery_attempts} previous automated recovery attempt(s); limit {MAX_AUTOMATED_RETRIES}")
        add("not_high_risk", payment.failure_reason not in HIGH_RISK_REASONS,
            f"Failure reason {payment.failure_reason.value} " + ("is high-risk; automation prohibited" if payment.failure_reason in HIGH_RISK_REASONS else "is not high-risk"))
        add("confidence_threshold", decision.confidence >= MIN_CONFIDENCE_FOR_AUTOMATION,
            f"Agent confidence {decision.confidence:.0%} vs minimum {MIN_CONFIDENCE_FOR_AUTOMATION:.0%}")
        add("escalation_always_allowed", True, "Escalation to a human is always a permitted action")

    allowed = final == proposed
    return PolicyVerdict(allowed=allowed, final_action=final, checks=checks, override_reason=override)


def describe_limits() -> dict:
    return {
        "max_automated_retries": MAX_AUTOMATED_RETRIES,
        "auto_action_amount_limit": AUTO_ACTION_AMOUNT_LIMIT,
        "min_confidence_for_automation": MIN_CONFIDENCE_FOR_AUTOMATION,
        "min_customer_success_rate_for_retry": MIN_CUSTOMER_SUCCESS_RATE_FOR_RETRY,
        "max_days_for_auto_retry": MAX_DAYS_FOR_AUTO_RETRY,
        "high_risk_reasons": sorted(r.value for r in HIGH_RISK_REASONS),
        "non_retryable_reasons": sorted(r.value for r in NON_RETRYABLE_REASONS),
    }
