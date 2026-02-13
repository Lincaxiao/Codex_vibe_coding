from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Iterable


def _to_utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def _from_utc_text(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def normalize_tags(raw: str | Iterable[str]) -> str:
    if isinstance(raw, str):
        pieces = raw.split(",")
    else:
        pieces = list(raw)

    clean: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        tag = piece.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        clean.append(tag)
    return ",".join(clean)


@dataclass(frozen=True)
class SessionRecord:
    start_time: datetime
    end_time: datetime
    duration_sec: int
    task: str
    tags: str
    kind: str
    completed: bool
    interrupted_reason: str | None = None


@dataclass(frozen=True)
class StoredSession:
    id: int
    start_time: datetime
    end_time: datetime
    duration_sec: int
    task: str
    tags: str
    kind: str
    completed: bool
    interrupted_reason: str | None


class FocusLogDB:
    def __init__(self, db_path: Path, journal_mode: str | None = None) -> None:
        self.db_path = Path(db_path)
        raw_mode = (journal_mode or os.getenv("FOCUSLOG_JOURNAL_MODE") or "MEMORY").strip()
        self.journal_mode = raw_mode.upper() if raw_mode else "MEMORY"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self._apply_journal_mode(conn)
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _apply_journal_mode(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(f"PRAGMA journal_mode={self.journal_mode}")
        except sqlite3.OperationalError:
            conn.execute("PRAGMA journal_mode=MEMORY")

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration_sec INTEGER NOT NULL CHECK (duration_sec >= 0),
                    task TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    kind TEXT NOT NULL CHECK (kind IN ('work', 'break')),
                    completed INTEGER NOT NULL CHECK (completed IN (0, 1)),
                    interrupted_reason TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_start_time
                ON sessions(start_time)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sessions_kind
                ON sessions(kind)
                """
            )
            conn.commit()

    def add_session(self, record: SessionRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    start_time,
                    end_time,
                    duration_sec,
                    task,
                    tags,
                    kind,
                    completed,
                    interrupted_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _to_utc_text(record.start_time),
                    _to_utc_text(record.end_time),
                    int(max(0, record.duration_sec)),
                    record.task.strip(),
                    normalize_tags(record.tags),
                    record.kind,
                    1 if record.completed else 0,
                    (record.interrupted_reason or "").strip() or None,
                ),
            )
            conn.commit()

    def list_sessions(
        self,
        since: datetime | None = None,
        tag: str | None = None,
        task_contains: str | None = None,
        limit: int = 20,
    ) -> list[StoredSession]:
        clauses = ["1=1"]
        params: list[object] = []

        if since is not None:
            clauses.append("start_time >= ?")
            params.append(_to_utc_text(since))
        if tag:
            clauses.append("instr(',' || lower(tags) || ',', ',' || ? || ',') > 0")
            params.append(tag.strip().lower())
        if task_contains:
            clauses.append("lower(task) LIKE ?")
            params.append(f"%{task_contains.strip().lower()}%")

        safe_limit = max(1, min(2000, int(limit)))
        query = (
            "SELECT id, start_time, end_time, duration_sec, task, tags, kind, completed, interrupted_reason "
            "FROM sessions "
            f"WHERE {' AND '.join(clauses)} "
            "ORDER BY start_time DESC "
            "LIMIT ?"
        )
        params.append(safe_limit)
        return self._read_sessions(query, params)

    def list_sessions_between(self, start: datetime, end: datetime) -> list[StoredSession]:
        query = (
            "SELECT id, start_time, end_time, duration_sec, task, tags, kind, completed, interrupted_reason "
            "FROM sessions "
            "WHERE start_time >= ? AND start_time < ? "
            "ORDER BY start_time ASC"
        )
        return self._read_sessions(query, [_to_utc_text(start), _to_utc_text(end)])

    def list_all_sessions(self) -> list[StoredSession]:
        query = (
            "SELECT id, start_time, end_time, duration_sec, task, tags, kind, completed, interrupted_reason "
            "FROM sessions "
            "ORDER BY start_time ASC"
        )
        return self._read_sessions(query, [])

    def _read_sessions(self, query: str, params: list[object]) -> list[StoredSession]:
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        items: list[StoredSession] = []
        for row in rows:
            items.append(
                StoredSession(
                    id=int(row["id"]),
                    start_time=_from_utc_text(row["start_time"]),
                    end_time=_from_utc_text(row["end_time"]),
                    duration_sec=int(row["duration_sec"]),
                    task=row["task"] or "",
                    tags=row["tags"] or "",
                    kind=row["kind"],
                    completed=bool(row["completed"]),
                    interrupted_reason=row["interrupted_reason"],
                )
            )
        return items


def default_db_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "focuslog.sqlite"
