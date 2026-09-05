"""SQLite persistence for payments, decisions and audit events."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get("RECOVERAI_DB", os.path.join(os.path.dirname(__file__), "recoverai.db"))


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    with conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
            );
            CREATE TABLE IF NOT EXISTS cases (
                payment_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status TEXT NOT NULL,
                amount_recovered REAL NOT NULL DEFAULT 0,
                decision_correct INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                step TEXT NOT NULL,
                message TEXT NOT NULL,
                data TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_payment ON audit(payment_id);
            """
        )


def reset_cases() -> None:
    with conn() as c:
        c.execute("DELETE FROM cases")
        c.execute("DELETE FROM audit")
        c.execute("UPDATE payments SET status='PENDING'")


# ---------- payments ----------

def upsert_payments(payments: List[Dict[str, Any]]) -> None:
    with conn() as c:
        c.executemany(
            "INSERT OR REPLACE INTO payments(payment_id, data, status) VALUES (?, ?, ?)",
            [(p["payment_id"], json.dumps(p), p.get("status", "PENDING")) for p in payments],
        )


def count_payments() -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]


def list_payments(status: Optional[str] = None, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
    with conn() as c:
        if status:
            rows = c.execute(
                "SELECT data, status FROM payments WHERE status=? ORDER BY payment_id LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT data, status FROM payments ORDER BY payment_id LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        d["status"] = r["status"]
        out.append(d)
    return out


def get_payment(payment_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT data, status FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
    if not r:
        return None
    d = json.loads(r["data"])
    d["status"] = r["status"]
    return d


def set_payment_status(payment_id: str, status: str) -> None:
    with conn() as c:
        c.execute("UPDATE payments SET status=? WHERE payment_id=?", (status, payment_id))


# ---------- cases ----------

def save_case(payment_id: str, case: Dict[str, Any], status: str, amount_recovered: float, correct: bool) -> None:
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO cases(payment_id, data, status, amount_recovered, decision_correct, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (payment_id, json.dumps(case), status, amount_recovered, int(correct), datetime.now(timezone.utc).isoformat()),
        )
        c.execute("UPDATE payments SET status=? WHERE payment_id=?", (status, payment_id))


def get_case(payment_id: str) -> Optional[Dict[str, Any]]:
    with conn() as c:
        r = c.execute("SELECT data FROM cases WHERE payment_id=?", (payment_id,)).fetchone()
    return json.loads(r["data"]) if r else None


def list_cases() -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT data FROM cases ORDER BY payment_id").fetchall()
    return [json.loads(r["data"]) for r in rows]


# ---------- audit ----------

def record_audit_event(payment_id: str, step: str, message: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with conn() as c:
        c.execute(
            "INSERT INTO audit(ts, payment_id, step, message, data) VALUES (?, ?, ?, ?, ?)",
            (ts, payment_id, step, message, json.dumps(data) if data is not None else None),
        )
    return {"ts": ts, "payment_id": payment_id, "step": step, "message": message, "data": data}


def get_audit(payment_id: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    with conn() as c:
        if payment_id:
            rows = c.execute(
                "SELECT ts, payment_id, step, message, data FROM audit WHERE payment_id=? ORDER BY id", (payment_id,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT ts, payment_id, step, message, data FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [
        {
            "ts": r["ts"],
            "payment_id": r["payment_id"],
            "step": r["step"],
            "message": r["message"],
            "data": json.loads(r["data"]) if r["data"] else None,
        }
        for r in rows
    ]
