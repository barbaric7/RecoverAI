"""Action executor.

Only *policy-approved* actions reach this module. It talks to a payment
provider through a tiny adapter interface:

  - SimulatedRazorpay  (default) — Razorpay-shaped responses, outcome drawn
                                   from the dataset's pre-rolled simulation.
  - RazorpayTestMode   (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET set and
                        RECOVERAI_PROVIDER=razorpay) — creates real test-mode
                        Payment Links / Orders via the REST API.

Retries in real Razorpay require a saved token/mandate; in test mode we
create an Order to represent the re-attempt and (for demo) treat the
simulated outcome as the settlement result.
"""
from __future__ import annotations

import base64
import os
import random
import time
import uuid
from typing import Protocol

import httpx

from models import Action, ExecutionResult, Payment

PROVIDER = os.environ.get("RECOVERAI_PROVIDER", "simulated")


class PaymentProvider(Protocol):
    name: str

    def retry(self, p: Payment) -> ExecutionResult: ...
    def payment_link(self, p: Payment) -> ExecutionResult: ...


# --------------------------------------------------------------------------
class SimulatedRazorpay:
    name = "razorpay-simulated"

    def _ref(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:14]}"

    def retry(self, p: Payment) -> ExecutionResult:
        time.sleep(0.002)  # pretend network
        outcome = p.simulated_outcome if p.simulated_outcome in ("SUCCESS", "FAIL") else "FAIL"
        ok = outcome == "SUCCESS"
        return ExecutionResult(
            action=Action.RETRY_PAYMENT,
            executed=True,
            provider=self.name,
            reference=self._ref("pay"),
            outcome=outcome,
            amount_recovered=p.amount if ok else 0.0,
            detail="Retry captured successfully" if ok else "Issuer declined the retry",
        )

    def payment_link(self, p: Payment) -> ExecutionResult:
        outcome = p.simulated_outcome if p.simulated_outcome in ("SUCCESS", "FAIL", "EXPIRED") else "EXPIRED"
        ok = outcome == "SUCCESS"
        ref = self._ref("plink")
        return ExecutionResult(
            action=Action.CREATE_PAYMENT_LINK,
            executed=True,
            provider=self.name,
            reference=ref,
            outcome=outcome,
            amount_recovered=p.amount if ok else 0.0,
            detail={
                "SUCCESS": f"Customer paid via link https://rzp.io/l/{ref[-8:]}",
                "FAIL": "Customer attempted payment via link; issuer declined",
                "EXPIRED": "Payment link expired without customer action",
            }[outcome],
        )


# --------------------------------------------------------------------------
class RazorpayTestMode:
    """Minimal REST adapter for Razorpay test mode (no SDK dependency)."""

    name = "razorpay-test"
    BASE = "https://api.razorpay.com/v1"

    def __init__(self) -> None:
        kid = os.environ["RAZORPAY_KEY_ID"]
        sec = os.environ["RAZORPAY_KEY_SECRET"]
        if not kid.startswith("rzp_test_"):
            raise RuntimeError("Refusing to run: RAZORPAY_KEY_ID is not a test-mode key")
        token = base64.b64encode(f"{kid}:{sec}".encode()).decode()
        self._h = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        self._sim = SimulatedRazorpay()

    def retry(self, p: Payment) -> ExecutionResult:
        # A real retry needs a customer token; we create an Order to represent
        # the re-attempt and use the pre-rolled outcome for settlement (demo).
        r = httpx.post(
            f"{self.BASE}/orders",
            headers=self._h,
            json={"amount": int(p.amount * 100), "currency": p.currency, "receipt": f"retry_{p.payment_id}",
                  "notes": {"recoverai": "retry", "payment_id": p.payment_id}},
            timeout=20,
        )
        r.raise_for_status()
        order = r.json()
        sim = self._sim.retry(p)
        sim.provider = self.name
        sim.reference = order["id"]
        sim.detail = f"Order {order['id']} created in test mode; " + sim.detail.lower()
        return sim

    def payment_link(self, p: Payment) -> ExecutionResult:
        r = httpx.post(
            f"{self.BASE}/payment_links",
            headers=self._h,
            json={
                "amount": int(p.amount * 100),
                "currency": p.currency,
                "description": f"RecoverAI recovery for {p.payment_id}",
                "reference_id": f"{p.payment_id}-{uuid.uuid4().hex[:6]}",
                "notes": {"recoverai": "payment_link", "payment_id": p.payment_id},
            },
            timeout=20,
        )
        r.raise_for_status()
        link = r.json()
        sim = self._sim.payment_link(p)
        sim.provider = self.name
        sim.reference = link["id"]
        sim.detail = f"Test-mode link {link.get('short_url')} created; simulated customer outcome: {sim.outcome}"
        return sim


def _provider() -> PaymentProvider:
    if PROVIDER == "razorpay" and os.environ.get("RAZORPAY_KEY_ID"):
        return RazorpayTestMode()
    return SimulatedRazorpay()


_prov: PaymentProvider | None = None


def provider() -> PaymentProvider:
    global _prov
    if _prov is None:
        _prov = _provider()
    return _prov


# --------------------------------------------------------------------------
def execute(p: Payment, action: Action) -> ExecutionResult:
    """Execute a policy-approved action. This is the ONLY money-movement path."""
    prov = provider()
    if action == Action.RETRY_PAYMENT:
        return prov.retry(p)
    if action == Action.WAIT_AND_RETRY:
        # Scheduled retry: in the batch simulation we fast-forward the wait.
        res = prov.retry(p)
        res.action = Action.WAIT_AND_RETRY
        res.detail = "Scheduled retry (T+2d) executed: " + res.detail.lower()
        return res
    if action == Action.CREATE_PAYMENT_LINK:
        return prov.payment_link(p)
    if action == Action.ESCALATE_TO_HUMAN:
        return ExecutionResult(
            action=action, executed=True, provider="human-review-queue",
            reference=f"case_{p.payment_id}", outcome="ESCALATED",
            detail="Case added to human review queue",
        )
    if action == Action.MARK_UNRECOVERABLE:
        return ExecutionResult(
            action=action, executed=True, provider="none", reference=None, outcome="SKIPPED",
            detail="No action taken; marked unrecoverable",
        )
    raise ValueError(f"unknown action {action}")
