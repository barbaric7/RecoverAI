"""The RecoverAI reasoning agent.

Observe (payment + history) -> Reason (LLM) -> Structured decision.

The LLM never touches Razorpay. It only emits a JSON recommendation, which
is then validated by policy.py and executed by actions.py.

If OPENAI_API_KEY is not set, or the call fails, a deterministic heuristic
fallback produces the decision so the pipeline always completes. Each
decision is tagged with its `source` so the dashboard can show which path
was used.
"""
from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from typing import Optional

from models import Action, AgentDecision, FailureReason, Payment

log = logging.getLogger("recoverai.agent")

_KEY = os.environ.get("OPENAI_API_KEY", "")
_IS_OPENROUTER = _KEY.startswith("sk-or-")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or ("https://openrouter.ai/api/v1" if _IS_OPENROUTER else None)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL") or ("openai/gpt-4.1" if _IS_OPENROUTER else "gpt-4o-mini")
LLM_ENABLED = bool(_KEY) and os.environ.get("RECOVERAI_USE_LLM", "1") != "0"
# Cap concurrent LLM calls (OpenRouter free-tier budgets reject parallel in-flight requests)
LLM_CONCURRENCY = int(os.environ.get("LLM_CONCURRENCY", "2" if _IS_OPENROUTER else "8"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))
_sem = threading.BoundedSemaphore(LLM_CONCURRENCY)

# Circuit breaker: after N consecutive budget/auth failures, stop calling the LLM for a cool-down
# window so a dead API key degrades to the fallback instantly instead of stalling the batch.
_BREAKER_THRESHOLD = int(os.environ.get("LLM_BREAKER_THRESHOLD", "3"))
_BREAKER_COOLDOWN = float(os.environ.get("LLM_BREAKER_COOLDOWN", "120"))
_breaker = {"failures": 0, "open_until": 0.0}
_breaker_lock = threading.Lock()


def breaker_state() -> dict:
    with _breaker_lock:
        return {"open": time.time() < _breaker["open_until"], "consecutive_failures": _breaker["failures"],
                "open_until": _breaker["open_until"]}


def _breaker_open() -> bool:
    with _breaker_lock:
        return time.time() < _breaker["open_until"]


def _breaker_record(success: bool, hard: bool) -> None:
    with _breaker_lock:
        if success:
            _breaker["failures"] = 0
            return
        if hard:
            _breaker["failures"] += 1
            if _breaker["failures"] >= _BREAKER_THRESHOLD:
                _breaker["open_until"] = time.time() + _BREAKER_COOLDOWN
                log.warning("LLM circuit breaker OPEN for %.0fs after %d consecutive budget/auth failures; using fallback",
                            _BREAKER_COOLDOWN, _breaker["failures"])

SYSTEM_PROMPT = """You are RecoverAI, an autonomous revenue recovery agent for a merchant payment system.

Your objective is to recover legitimate lost revenue while minimizing customer friction, repeated failed attempts, and unsafe actions.

You receive information about a failed payment, including: payment amount, failure reason, number of previous attempts, customer payment history, customer success rate, subscription status, time since failure, and previous recovery attempts.

Your responsibilities:
1. Diagnose the likely reason for payment failure.
2. Determine whether the payment is potentially recoverable.
3. Select the most appropriate recovery strategy.
4. Explain why the strategy was selected.
5. Never exceed the limits defined by the policy engine.
6. Stop recovery attempts when a stopping rule is triggered.
7. Escalate cases that are uncertain, high-risk, or outside policy.
8. Never invent payment outcomes or customer information.
9. Record a concise audit explanation for every decision.

Available actions:
- RETRY_PAYMENT: immediately re-attempt the charge with the same credential (transient bank/gateway failures).
- CREATE_PAYMENT_LINK: send the customer a fresh payment link (expired card, auth failure, abandoned checkout, weak history).
- WAIT_AND_RETRY: schedule a retry in 2-3 days (insufficient funds, likely salary-cycle timing).
- ESCALATE_TO_HUMAN: route to a human reviewer (high value, repeated failures, fraud/blocked signals, low confidence).
- MARK_UNRECOVERABLE: stop; no further action (cancelled subscription, exhausted attempts with weak history, already-paid).

Policy limits you must respect (the policy engine enforces them independently):
- Maximum 2 automated retry attempts per payment (attempt_count must be < 2 to retry).
- Automated actions only below ₹10,000; at or above that, escalate.
- SUSPECTED_FRAUD and CARD_BLOCKED always escalate.
- Never retry a payment that has already succeeded (payment_already_succeeded=true → MARK_UNRECOVERABLE).
- Expired cards must not be retried with the same credential; use a payment link.
- If more than 2 previous recovery attempts have been made, escalate.
- If confidence is low (< 0.55), escalate rather than guess.
- Failures older than 7 days must not be auto-retried; escalate instead (payment links for expired card / auth / abandoned checkout are still fine).

Decision principles:
- Temporary failures (bank timeout, bank error, payment timeout) with strong payment history (success rate ≥ 60%) → RETRY_PAYMENT.
- Insufficient funds with a reasonable history (≥ 50%) → WAIT_AND_RETRY; weak history → CREATE_PAYMENT_LINK.
- Expired card, authentication failure, abandoned checkout → CREATE_PAYMENT_LINK.
- Subscription failure: cancelled subscription → MARK_UNRECOVERABLE; strong history (≥ 70%) → RETRY_PAYMENT; else payment link.
- Repeated failures or exhausted attempts: success rate ≥ 50% → ESCALATE_TO_HUMAN; else MARK_UNRECOVERABLE.
- Repeated failures should never trigger unlimited retries.
- High-value or unusual transactions require stricter verification.

expected_recovery = amount × your estimated probability of recovery (0 for escalate/unrecoverable).

Return ONLY valid JSON, no prose, in exactly this structure:
{
  "payment_id": "...",
  "diagnosis": "one or two sentences",
  "recoverable": true,
  "confidence": 0.0,
  "recommended_action": "RETRY_PAYMENT | CREATE_PAYMENT_LINK | WAIT_AND_RETRY | ESCALATE_TO_HUMAN | MARK_UNRECOVERABLE",
  "reason": "one or two sentences",
  "expected_recovery": 0.0,
  "escalation_required": false,
  "policy_checks": ["short list of the policy rules you considered"]
}"""


def build_context(p: Payment) -> dict:
    """Observation the agent reasons over. Ground-truth fields are excluded."""
    return {
        "payment_id": p.payment_id,
        "customer_id": p.customer_id,
        "amount": p.amount,
        "currency": p.currency,
        "failure_reason": p.failure_reason.value,
        "failure_message": p.failure_message,
        "attempt_count": p.attempt_count,
        "customer_history": {
            "previous_payments": p.previous_payments,
            "success_rate": p.customer_success_rate,
            "subscription_status": p.subscription_status,
        },
        "days_since_failure": p.days_since_failure,
        "previous_recovery_attempts": p.previous_recovery_attempts,
        "payment_already_succeeded": p.payment_already_succeeded,
    }


# --------------------------------------------------------------------------
# Deterministic fallback (also used when LLM disabled)
# --------------------------------------------------------------------------

def heuristic_decision(p: Payment) -> AgentDecision:
    r = p.failure_reason
    sr = p.customer_success_rate
    conf = 0.7
    checks = [
        f"attempt_count={p.attempt_count} vs retry limit 2",
        f"amount ₹{p.amount:,.0f} vs auto limit ₹10,000",
        f"customer success rate {sr:.0%}",
    ]

    def d(action: Action, diag: str, reason: str, conf: float, prob: float) -> AgentDecision:
        recoverable = action in (Action.RETRY_PAYMENT, Action.CREATE_PAYMENT_LINK, Action.WAIT_AND_RETRY)
        return AgentDecision(
            payment_id=p.payment_id,
            diagnosis=diag,
            recoverable=recoverable,
            confidence=round(conf, 2),
            recommended_action=action,
            reason=reason,
            expected_recovery=round(p.amount * prob, 2) if recoverable else 0.0,
            escalation_required=action == Action.ESCALATE_TO_HUMAN,
            policy_checks=checks,
            source="fallback",
        )

    if p.payment_already_succeeded:
        return d(Action.MARK_UNRECOVERABLE, "Stale failure event; payment already succeeded.",
                 "No revenue at risk. Any action would risk a double charge.", 0.98, 0)
    if r in (FailureReason.SUSPECTED_FRAUD, FailureReason.CARD_BLOCKED):
        return d(Action.ESCALATE_TO_HUMAN, f"{r.value.replace('_', ' ').title()} signal from issuer.",
                 "Risk signals require human review; automation prohibited.", 0.9, 0)
    if p.amount >= 10000:
        return d(Action.ESCALATE_TO_HUMAN, "High-value transaction above automation threshold.",
                 "Amount exceeds ₹10,000 auto-action limit; a human must approve any recovery.", 0.85, 0)
    if p.attempt_count >= 2 or p.previous_recovery_attempts >= 2:
        if sr >= 0.5:
            return d(Action.ESCALATE_TO_HUMAN, "Automated recovery budget exhausted.",
                     f"Further automated attempts could create customer friction; recovery probability ~{sr*0.5:.0%}. Human review required.",
                     0.6, 0)
        return d(Action.MARK_UNRECOVERABLE, "Repeated failures with weak payment history.",
                 "Low likelihood of recovery; stopping to avoid friction.", 0.7, 0)
    if p.days_since_failure > 7 and r in (FailureReason.BANK_TIMEOUT, FailureReason.BANK_ERROR, FailureReason.PAYMENT_TIMEOUT,
                                          FailureReason.INSUFFICIENT_FUNDS, FailureReason.SUBSCRIPTION_FAILURE):
        return d(Action.ESCALATE_TO_HUMAN, "Failure is stale (>7 days).",
                 "Too old for automated retry; a human should decide whether to pursue.", 0.7, 0)
    if r in (FailureReason.BANK_TIMEOUT, FailureReason.BANK_ERROR, FailureReason.PAYMENT_TIMEOUT):
        if sr >= 0.6:
            return d(Action.RETRY_PAYMENT, "High probability of transient failure at bank/gateway.",
                     "Customer has strong payment history and the failure appears temporary.", 0.6 + 0.35 * sr, 0.55 + 0.35 * sr)
        return d(Action.CREATE_PAYMENT_LINK, "Transient failure but weak customer history.",
                 "Let the customer re-initiate via a fresh link rather than burning a retry.", 0.65, 0.4)
    if r == FailureReason.INSUFFICIENT_FUNDS:
        if sr >= 0.5:
            return d(Action.WAIT_AND_RETRY, "Insufficient balance; likely timing-related.",
                     "Retry after a short delay when funds are more likely to be available.", 0.72, 0.5)
        return d(Action.CREATE_PAYMENT_LINK, "Insufficient balance with weak history.",
                 "Customer should choose an alternate method via payment link.", 0.6, 0.35)
    if r in (FailureReason.EXPIRED_CARD, FailureReason.AUTH_FAILURE, FailureReason.CHECKOUT_ABANDONED):
        return d(Action.CREATE_PAYMENT_LINK, f"{r.value.replace('_', ' ').title()}: requires customer action.",
                 "Retrying the same credential cannot succeed; a payment link lets the customer fix it.", 0.8, 0.5)
    if r == FailureReason.SUBSCRIPTION_FAILURE:
        if p.subscription_status == "CANCELLED":
            return d(Action.MARK_UNRECOVERABLE, "Subscription cancelled by customer.",
                     "No legitimate revenue to recover.", 0.9, 0)
        if sr >= 0.7:
            return d(Action.RETRY_PAYMENT, "Recurring debit failed; customer historically reliable.",
                     "Retry the mandate debit once.", 0.75, 0.6)
        return d(Action.CREATE_PAYMENT_LINK, "Recurring debit failed; mixed history.",
                 "Ask customer to pay this cycle manually.", 0.65, 0.45)
    if r == FailureReason.REPEATED_FAILURE:
        if sr >= 0.5:
            return d(Action.ESCALATE_TO_HUMAN, "Repeated declines on this payment.", "Human review needed.", 0.6, 0)
        return d(Action.MARK_UNRECOVERABLE, "Repeated declines with weak history.", "Stop to avoid friction.", 0.7, 0)
    return d(Action.ESCALATE_TO_HUMAN, "Unrecognised failure pattern.", "Low confidence; escalate.", 0.4, 0)


# --------------------------------------------------------------------------
# LLM path
# --------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # imported lazily so the app runs without the package

        kw = {"api_key": _KEY}
        if OPENAI_BASE_URL:
            kw["base_url"] = OPENAI_BASE_URL
            kw["default_headers"] = {"HTTP-Referer": "https://github.com/recoverai", "X-Title": "RecoverAI"}
        _client = OpenAI(**kw)
    return _client


def _call_llm(ctx: dict) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=400,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Failed payment case:\n" + json.dumps(ctx, indent=2)},
        ],
        timeout=30,
    )
    return resp.choices[0].message.content or "{}"


def llm_decision(p: Payment) -> Optional[AgentDecision]:
    if _breaker_open():
        return None
    ctx = build_context(p)
    last_exc: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            with _sem:
                raw = _call_llm(ctx)
            _breaker_record(True, False)
            data = json.loads(raw)
            data["payment_id"] = p.payment_id  # never trust the model to echo ids
            data.setdefault("policy_checks", [])
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            data["expected_recovery"] = max(0.0, float(data.get("expected_recovery", 0.0)))
            data["source"] = "llm"
            return AgentDecision(**data)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            code = getattr(exc, "status_code", None)
            hard = code in (401, 402, 403)  # budget / auth: retrying rarely helps
            _breaker_record(False, hard)
            transient = code in (408, 409, 429, 500, 502, 503, 504) or (code == 402 and attempt == 0) or code is None
            if not transient or attempt == LLM_MAX_RETRIES or _breaker_open():
                break
            # honour Retry-After if present, but cap it; otherwise exponential backoff w/ jitter
            wait = 1.5 * (2 ** attempt) + random.random()
            try:
                ra = getattr(exc, "response", None).headers.get("retry-after")  # type: ignore[union-attr]
                if ra:
                    wait = min(float(ra), 8.0)
            except Exception:  # noqa: BLE001
                pass
            log.info("LLM transient error (%s) for %s; retry %d/%d in %.1fs", code, p.payment_id, attempt + 1, LLM_MAX_RETRIES, wait)
            time.sleep(wait)
    log.warning("LLM decision failed for %s: %s", p.payment_id, str(last_exc)[:160])
    return None


def decide(p: Payment, use_llm: Optional[bool] = None) -> AgentDecision:
    use = LLM_ENABLED if use_llm is None else use_llm
    if use:
        d = llm_decision(p)
        if d is not None:
            return d
    return heuristic_decision(p)
