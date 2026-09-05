"""End-to-end tests for the orchestrator loop and the HTTP API.

Run:  python -m pytest -q
"""
import os
import tempfile

import pytest

os.environ["RECOVERAI_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["RECOVERAI_USE_LLM"] = "0"

import database as db  # noqa: E402
import dataset  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from orchestrator import run_case  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def seed():
    db.init_db()
    db.upsert_payments(dataset.generate())
    yield


def test_happy_path_retry_recovers_and_audits():
    case = run_case("P0042", use_llm=False)
    assert case.decision.recommended_action.value == "RETRY_PAYMENT"
    assert case.policy.allowed
    assert case.execution.outcome == "SUCCESS"
    assert case.status.value == "RECOVERED"
    assert case.execution.amount_recovered == 2499.0
    steps = [e["step"] for e in db.get_audit("P0042")]
    # reasoning + policy are logged BEFORE the action
    assert steps.index("POLICY") < steps.index("ACT") < steps.index("VERIFY")
    assert steps[-1] == "OUTCOME"


def test_stale_event_never_executes_money_movement():
    case = run_case("P0210", use_llm=False)
    assert case.payment.payment_already_succeeded
    assert case.policy.final_action.value == "MARK_UNRECOVERABLE"
    assert case.execution.provider == "none"
    assert case.execution.amount_recovered == 0


def test_high_value_is_escalated_even_if_agent_wants_to_retry(monkeypatch):
    """Force the agent to propose RETRY on a ₹12,999 case; policy must block it."""
    import agent
    from models import Action, AgentDecision

    def rogue(p, use_llm=None):
        return AgentDecision(payment_id=p.payment_id, diagnosis="x", recoverable=True, confidence=0.95,
                             recommended_action=Action.RETRY_PAYMENT, reason="yolo", expected_recovery=p.amount)

    monkeypatch.setattr(agent, "decide", rogue)
    case = run_case("P0099", use_llm=False)
    assert case.decision.recommended_action == Action.RETRY_PAYMENT
    assert not case.policy.allowed
    assert case.policy.final_action == Action.ESCALATE_TO_HUMAN
    assert case.status.value == "ESCALATED"
    assert case.execution.provider == "human-review-queue"
    pol = [e for e in db.get_audit("P0099") if e["step"] == "POLICY"][-1]
    assert "BLOCKED" in pol["message"]


def test_failed_retry_is_unresolved_not_retried_again():
    case = run_case("P0117", use_llm=False)
    assert case.policy.final_action.value == "RETRY_PAYMENT"
    assert case.execution.outcome == "FAIL"
    assert case.status.value == "UNRESOLVED"
    # exactly one ACT event: no silent second retry
    assert sum(1 for e in db.get_audit("P0117") if e["step"] == "ACT") == 1


def test_api_recover_and_metrics():
    client = TestClient(app)
    r = client.post("/api/agent/recover/P0003?use_llm=false")
    assert r.status_code == 200
    body = r.json()
    assert body["policy"]["final_action"] == "CREATE_PAYMENT_LINK"
    assert body["status"] == "RECOVERED"
    m = client.get("/api/metrics").json()
    assert m["processed"] >= 1 and m["recovered_amount"] >= 8999
    a = client.get("/api/audit?payment_id=P0003").json()["items"]
    assert [e["step"] for e in a][:2] == ["EVENT", "OBSERVE"]
    assert client.get("/api/payments/NOPE").status_code == 404
