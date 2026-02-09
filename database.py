import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path('test1.sqlite3')


class SilentDatabase:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    last_seen_timestamp TEXT NOT NULL
                )
                '''
            )
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    bot_a_seconds REAL,
                    bot_b_seconds REAL,
                    total_seconds REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                '''
            )

    def upsert_user(self, telegram_id: int, username: Optional[str], full_name: str, ts: str) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO users (telegram_id, username, full_name, last_seen_timestamp)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=excluded.username,
                    full_name=excluded.full_name,
                    last_seen_timestamp=excluded.last_seen_timestamp
                ''',
                (telegram_id, username or '', full_name, ts),
            )

    def insert_search_event(
        self,
        telegram_id: int,
        target: str,
        mode: str,
        status: str,
        bot_a_seconds: Optional[float],
        bot_b_seconds: Optional[float],
        total_seconds: float,
        created_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO searches (
                    telegram_id, target, mode, status,
                    bot_a_seconds, bot_b_seconds, total_seconds, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    telegram_id,
                    target,
                    mode,
                    status,
                    bot_a_seconds,
                    bot_b_seconds,
                    total_seconds,
                    created_at,
                ),
            )

    def total_users(self) -> int:
        with self._connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM users').fetchone()
            return int(row[0] if row else 0)
