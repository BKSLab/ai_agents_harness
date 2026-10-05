"""Local mutation journal for GitLab writes; shares the Bitrix journal table with a distinct scope."""

from pathlib import Path

from bitrix_state import Journal as _BaseJournal, digest
from gitlab_config import state_home


class Journal(_BaseJournal):
    def __init__(self, config, path=None):
        self.config = config
        # The "gitlab" prefix keeps GitLab scopes disjoint from Bitrix scopes in the shared table.
        self.scope = digest(["gitlab", config.host])
        self.path = Path(path or state_home() / "operations.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations (
                scope TEXT, operation_id TEXT, fingerprint TEXT, method TEXT, state TEXT,
                receipt TEXT, error_code TEXT, updated_at REAL,
                 PRIMARY KEY(scope, operation_id))""")

    def run(self, operation_id, method, payload, action):
        # Redact before the base journal persists a receipt, including server-controlled strings.
        receipt, replayed = super().run(operation_id, method, payload, lambda: self.config.redact(action()))
        # Older receipts may predate redaction; never return their credentials to callers.
        return self.config.redact(receipt), replayed
