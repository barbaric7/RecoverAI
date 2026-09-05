"""Policy engine tests: prove that unsafe LLM recommendations are blocked.

Run:  python -m pytest test_policy.py -q      (or)   python test_policy.py
"""
from models import Action, AgentDecision, FailureReason, Payment
import policy


def mk(**kw) -> Payment:
    base = dict(
        payment_id="T001", customer_id="C1", amount=1999.0, currency="INR",
        failure_reason=FailureReason.BANK_TIMEOUT, failure_message="x", attempt_count=0,
        customer_success_rate=0.9, previous_payments=10, subscription_status="NONE",
        days_since_failure=0.1, previous_recovery_attempts=0, payment_already_succeeded=False,
        ground_truth_recoverable=True, ground_truth_action=Action.RETRY_PAYMENT, simulated_outcome="SUCCESS",
    )
    base.update(kw)
    return Payment(**base)


def rec(action: Action, conf: float = 0.9) -> AgentDecision:
    return AgentDecision(payment_id="T001", diagnosis="d", recoverable=True, confidence=conf,
                         recommended_action=action, reason="r", expected_recovery=0)


def test_happy_retry_allowed():
    v = policy.evaluate(mk(), rec(Action.RETRY_PAYMENT))
    assert v.allowed and v.final_action == Action.RETRY_PAYMENT


def test_blocks_retry_after_success():
    v = policy.evaluate(mk(payment_already_succeeded=True), rec(Action.RETRY_PAYMENT))
    assert not v.allowed and v.final_action == Action.MARK_UNRECOVERABLE


def test_blocks_high_value_retry():
    v = policy.evaluate(mk(amount=15999), rec(Action.RETRY_PAYMENT))
    assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_blocks_high_value_payment_link():
    v = policy.evaluate(mk(amount=25000), rec(Action.CREATE_PAYMENT_LINK))
    assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_retry_limit():
    v = policy.evaluate(mk(attempt_count=2), rec(Action.RETRY_PAYMENT))
    assert v.final_action == Action.ESCALATE_TO_HUMAN
    assert any(c.name == "retry_limit" and not c.passed for c in v.checks)


def test_recovery_budget():
    v = policy.evaluate(mk(previous_recovery_attempts=2), rec(Action.WAIT_AND_RETRY))
    assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_expired_card_downgraded_to_link():
    v = policy.evaluate(mk(failure_reason=FailureReason.EXPIRED_CARD), rec(Action.RETRY_PAYMENT))
    assert v.final_action == Action.CREATE_PAYMENT_LINK


def test_fraud_never_automated():
    for a in (Action.RETRY_PAYMENT, Action.CREATE_PAYMENT_LINK, Action.WAIT_AND_RETRY):
        v = policy.evaluate(mk(failure_reason=FailureReason.SUSPECTED_FRAUD), rec(a))
        assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_low_confidence_escalates():
    v = policy.evaluate(mk(), rec(Action.RETRY_PAYMENT, conf=0.3))
    assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_weak_customer_downgraded():
    v = policy.evaluate(mk(customer_success_rate=0.2), rec(Action.RETRY_PAYMENT))
    assert v.final_action == Action.CREATE_PAYMENT_LINK


def test_premature_giveup_escalated():
    v = policy.evaluate(mk(customer_success_rate=0.95), rec(Action.MARK_UNRECOVERABLE))
    assert v.final_action == Action.ESCALATE_TO_HUMAN


def test_escalation_always_allowed():
    v = policy.evaluate(mk(amount=99999, attempt_count=5), rec(Action.ESCALATE_TO_HUMAN))
    assert v.allowed and v.final_action == Action.ESCALATE_TO_HUMAN


if __name__ == "__main__":
    import sys
    fns = [f for n, f in globals().items() if n.startswith("test_")]
    failed = 0
    for f in fns:
        try:
            f(); print(f"✓ {f.__name__}")
        except AssertionError:
            failed += 1; print(f"✗ {f.__name__}")
    print(f"\n{len(fns) - failed}/{len(fns)} policy tests passed")
    sys.exit(1 if failed else 0)
