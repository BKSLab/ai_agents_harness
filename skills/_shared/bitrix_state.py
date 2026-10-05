"""Local mutation journal; stores hashes and receipts, never request text or credentials."""

import hashlib
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time

from bitrix_config import ToolError, state_home


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class Journal:
    def __init__(self, config, path=None):
        self.scope = digest([config.portal, config.webhook_user_id])
        self.path = Path(path or state_home() / "operations.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations (
                scope TEXT, operation_id TEXT, fingerprint TEXT, method TEXT, state TEXT,
                receipt TEXT, error_code TEXT, updated_at REAL,
                PRIMARY KEY(scope, operation_id))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def run(self, operation_id, method, payload, action):
        if not operation_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", operation_id):
            raise ToolError("OPERATION_ID_REQUIRED", "Writes require a stable --operation-id (8-100 letters, digits, - or _).")
        fingerprint = digest([method, payload])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT fingerprint,state,receipt FROM operations WHERE scope=? AND operation_id=?",
                             (self.scope, operation_id)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise ToolError("OPERATION_CONFLICT", "This operation ID belongs to different input.")
                if row[1] == "succeeded":
                    return json.loads(row[2]), True
                raise ToolError("RECONCILE_REQUIRED", "Previous attempt is recorded. Verify its outcome before any new write.",
                                uncertain=row[1] in ("pending", "unknown"))
            db.execute("INSERT INTO operations VALUES (?,?,?,?,?,?,?,?)",
                       (self.scope, operation_id, fingerprint, method, "pending", None, None, time.time()))
        try:
            receipt = action()
        except ToolError as exc:
            self.finish(operation_id, "unknown" if exc.uncertain else "failed", error=exc.code)
            raise
        except BaseException:
            self.finish(operation_id, "unknown", error="INTERRUPTED")
            raise
        self.finish(operation_id, "succeeded", receipt=receipt)
        return receipt, False

    def finish(self, operation_id, state, receipt=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE operations SET state=?,receipt=?,error_code=?,updated_at=? WHERE scope=? AND operation_id=?",
                       (state, json.dumps(receipt), error, time.time(), self.scope, operation_id))

    def recent(self, limit=20):
        with self.connect() as db:
            rows = db.execute("SELECT operation_id,method,state,error_code,updated_at FROM operations WHERE scope=? "
                              "ORDER BY updated_at DESC LIMIT ?", (self.scope, limit)).fetchall()
        return [dict(zip(("operation_id", "method", "state", "error_code", "updated_at"), row)) for row in rows]
