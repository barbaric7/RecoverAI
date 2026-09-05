"""RecoverAI FastAPI backend."""
from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

import agent  # noqa: E402
import database as db  # noqa: E402
import dataset  # noqa: E402
import metrics  # noqa: E402
import policy  # noqa: E402
from orchestrator import run_case  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("recoverai")

app = FastAPI(title="RecoverAI", version="0.1.0", description="Autonomous Revenue Recovery Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---- batch run state ----
_run_lock = threading.Lock()
_run_state = {"running": False, "done": 0, "total": 0, "started_at": None, "finished_at": None, "error": None}


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    if db.count_payments() == 0:
        recs = dataset.generate()
        db.upsert_payments(recs)
        dataset.write_csv(recs, os.path.join(os.path.dirname(__file__), "..", "data", "payments.csv"))
        log.info("seeded %d synthetic payments", len(recs))
    log.info("LLM enabled: %s (model=%s)", agent.LLM_ENABLED, agent.OPENAI_MODEL)


# ---------------------------------------------------------------- health
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm_enabled": agent.LLM_ENABLED,
        "model": agent.OPENAI_MODEL if agent.LLM_ENABLED else None,
        "provider": os.environ.get("RECOVERAI_PROVIDER", "simulated"),
        "payments": db.count_payments(),
        "llm_sample": int(os.environ["LLM_SAMPLE"]) if os.environ.get("LLM_SAMPLE") else None,
        "breaker": agent.breaker_state(),
    }


@app.get("/api/policy")
def get_policy():
    return policy.describe_limits()


# ---------------------------------------------------------------- payments
@app.get("/api/payments")
def list_payments(status: Optional[str] = None, limit: int = Query(1000, le=5000), offset: int = 0):
    rows = db.list_payments(status=status, limit=limit, offset=offset)
    # strip labels from list view (they're still available on the case)
    slim = [
        {k: r[k] for k in ("payment_id", "customer_id", "amount", "currency", "failure_reason", "attempt_count",
                            "customer_success_rate", "previous_payments", "subscription_status", "days_since_failure",
                            "previous_recovery_attempts", "status")}
        for r in rows
    ]
    return {"count": len(slim), "items": slim}


@app.get("/api/payments/{payment_id}")
def get_payment(payment_id: str):
    p = db.get_payment(payment_id)
    if not p:
        raise HTTPException(404, "payment not found")
    case = db.get_case(payment_id)
    return {"payment": p, "case": case}


# ---------------------------------------------------------------- agent
@app.post("/api/agent/analyze/{payment_id}")
def analyze(payment_id: str, use_llm: Optional[bool] = None):
    """Dry run: agent recommendation + policy verdict, no execution."""
    from models import Payment

    raw = db.get_payment(payment_id)
    if not raw:
        raise HTTPException(404, "payment not found")
    p = Payment(**raw)
    decision = agent.decide(p, use_llm=use_llm)
    verdict = policy.evaluate(p, decision)
    return {"payment": raw, "decision": decision, "policy": verdict}


@app.post("/api/agent/recover/{payment_id}")
def recover_one(payment_id: str, use_llm: Optional[bool] = None):
    try:
        case = run_case(payment_id, use_llm=use_llm)
    except KeyError:
        raise HTTPException(404, "payment not found")
    return case


DEMO_IDS = ["P0042", "P0003", "P0099", "P0117", "P0210"]


def _batch(ids, use_llm: Optional[bool], workers: int, llm_ids: Optional[set] = None):
    _run_state.update({"running": True, "done": 0, "total": len(ids), "started_at": time.time(), "finished_at": None, "error": None})
    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(run_case, pid, (pid in llm_ids) if llm_ids is not None else use_llm) for pid in ids]
            for _ in as_completed(futs):
                _run_state["done"] += 1
    except Exception as exc:  # noqa: BLE001
        log.exception("batch failed")
        _run_state["error"] = str(exc)
    finally:
        _run_state["running"] = False
        _run_state["finished_at"] = time.time()


@app.post("/api/agent/recover")
def recover_batch(limit: Optional[int] = None, use_llm: Optional[bool] = None, reset: bool = True, workers: int = 8,
                  llm_sample: Optional[int] = None):
    """Run the recovery loop over all pending payments (background).

    llm_sample=N → hybrid mode: the LLM decides the demo cases + the first N-5 pending payments;
    the deterministic fallback handles the rest. Useful on tight API budgets. Every decision is
    tagged with its source (llm | fallback) so metrics stay honest.
    """
    if _run_state["running"]:
        raise HTTPException(409, "a batch run is already in progress")
    if reset:
        db.reset_cases()
    ids = [p["payment_id"] for p in db.list_payments(status="PENDING")]
    if limit:
        ids = ids[:limit]
    if not ids:
        return {"started": False, "message": "no pending payments", **_run_state}
    effective_llm = agent.LLM_ENABLED if use_llm is None else use_llm
    # In LLM mode, don't outrun the LLM concurrency cap (see agent.LLM_CONCURRENCY)
    workers = max(1, min(workers, agent.LLM_CONCURRENCY * 2 if effective_llm else 4))
    threading.Thread(target=_batch, args=(ids, use_llm, workers), daemon=True).start()
    return {"started": True, "total": len(ids), "llm": effective_llm}


@app.get("/api/agent/status")
def run_status():
    return _run_state


@app.post("/api/reset")
def reset():
    if _run_state["running"]:
        raise HTTPException(409, "cannot reset during a run")
    db.reset_cases()
    return {"ok": True}


# ---------------------------------------------------------------- metrics + audit
@app.get("/api/metrics")
def get_metrics():
    return metrics.compute()


@app.get("/api/cases")
def list_cases(status: Optional[str] = None):
    cases = db.list_cases()
    if status:
        cases = [c for c in cases if c["status"] == status]
    return {
        "count": len(cases),
        "items": [
            {
                "payment_id": c["payment"]["payment_id"],
                "amount": c["payment"]["amount"],
                "failure_reason": c["payment"]["failure_reason"],
                "recommended_action": c["decision"]["recommended_action"],
                "final_action": c["policy"]["final_action"],
                "policy_allowed": c["policy"]["allowed"],
                "confidence": c["decision"]["confidence"],
                "outcome": c["execution"]["outcome"],
                "status": c["status"],
                "amount_recovered": c["execution"]["amount_recovered"],
                "decision_correct": c["decision_correct"],
                "source": c["decision"].get("source", "llm"),
            }
            for c in cases
        ],
    }


@app.get("/api/audit")
def audit(payment_id: Optional[str] = None, limit: int = Query(200, le=2000)):
    return {"items": db.get_audit(payment_id=payment_id, limit=limit)}


# ---------------------------------------------------------------- static frontend (production build)
_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        return FileResponse(os.path.join(_dist, "index.html"))
