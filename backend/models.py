"""Pydantic models shared across the RecoverAI backend."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Action(str, Enum):
    RETRY_PAYMENT = "RETRY_PAYMENT"
    CREATE_PAYMENT_LINK = "CREATE_PAYMENT_LINK"
    WAIT_AND_RETRY = "WAIT_AND_RETRY"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
    MARK_UNRECOVERABLE = "MARK_UNRECOVERABLE"


class FailureReason(str, Enum):
    BANK_TIMEOUT = "BANK_TIMEOUT"
    BANK_ERROR = "BANK_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    EXPIRED_CARD = "EXPIRED_CARD"
    AUTH_FAILURE = "AUTH_FAILURE"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    REPEATED_FAILURE = "REPEATED_FAILURE"
    CHECKOUT_ABANDONED = "CHECKOUT_ABANDONED"
    SUBSCRIPTION_FAILURE = "SUBSCRIPTION_FAILURE"
    CARD_BLOCKED = "CARD_BLOCKED"
    SUSPECTED_FRAUD = "SUSPECTED_FRAUD"


class CaseStatus(str, Enum):
    PENDING = "PENDING"
    RECOVERED = "RECOVERED"
    ESCALATED = "ESCALATED"
    UNRESOLVED = "UNRESOLVED"
    UNRECOVERABLE = "UNRECOVERABLE"
    WAITING = "WAITING"


class Payment(BaseModel):
    payment_id: str
    customer_id: str
    amount: float
    currency: str = "INR"
    failure_reason: FailureReason
    failure_message: str
    attempt_count: int
    customer_success_rate: float
    previous_payments: int
    subscription_status: str  # ACTIVE | NONE | PAST_DUE | CANCELLED
    days_since_failure: float
    previous_recovery_attempts: int
    payment_already_succeeded: bool = False
    ground_truth_recoverable: bool
    ground_truth_action: Action
    simulated_outcome: str  # SUCCESS | FAIL | EXPIRED | N/A
    status: CaseStatus = CaseStatus.PENDING


class AgentDecision(BaseModel):
    """Structured output the LLM must produce."""

    payment_id: str
    diagnosis: str
    recoverable: bool
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_action: Action
    reason: str
    expected_recovery: float = Field(ge=0.0)
    escalation_required: bool = False
    policy_checks: List[str] = []
    source: str = "llm"  # llm | fallback


class PolicyCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class PolicyVerdict(BaseModel):
    allowed: bool
    final_action: Action
    checks: List[PolicyCheck]
    override_reason: Optional[str] = None


class ExecutionResult(BaseModel):
    action: Action
    executed: bool
    provider: str
    reference: Optional[str] = None
    outcome: str  # SUCCESS | FAIL | EXPIRED | PENDING | SKIPPED | ESCALATED
    amount_recovered: float = 0.0
    detail: str = ""


class CaseResult(BaseModel):
    payment: Payment
    decision: AgentDecision
    policy: PolicyVerdict
    execution: ExecutionResult
    status: CaseStatus
    decision_correct: bool


class AuditEvent(BaseModel):
    ts: str
    payment_id: str
    step: str
    message: str
    data: Optional[dict] = None
