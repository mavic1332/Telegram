from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from app.config import settings


class AuditLogger:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.audit_db_path
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    search_type TEXT,
                    outcome TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def log(self, chat_id: int, search_type: str, outcome: str, duration_ms: int) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO audit_logs(ts, chat_id, search_type, outcome, duration_ms) VALUES (?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), chat_id, search_type, outcome, duration_ms),
            )
            conn.commit()
