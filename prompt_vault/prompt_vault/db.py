from __future__ import annotations

import hashlib
import sqlite3
from sqlite3 import IntegrityError
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def default_db_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "prompt_vault.sqlite"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_hash(title: str, body: str) -> str:
    return hashlib.sha256(f"{title}\n{body}".encode("utf-8")).hexdigest()


def tokenize(text: str) -> list[str]:
    clean = []
    current = []
    for ch in text.lower():
        if ch.isalnum() or ch in {"_", "-"}:
            current.append(ch)
        else:
            if current:
                clean.append("".join(current))
                current = []
    if current:
        clean.append("".join(current))
    dedup = []
    seen = set()
    for token in clean:
        if token not in seen:
            seen.add(token)
            dedup.append(token)
    return dedup


@dataclass
class PromptRecord:
    id: int
    title: str
    body: str
    created_at: str
    updated_at: str
    is_deleted: int


class PromptDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_db_path()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_deleted INTEGER NOT NULL DEFAULT 0
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_prompts_content_hash ON prompts(content_hash);

                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS prompt_tags (
                    prompt_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY(prompt_id, tag_id),
                    FOREIGN KEY(prompt_id) REFERENCES prompts(id),
                    FOREIGN KEY(tag_id) REFERENCES tags(id)
                );
                """
            )

    def add_prompt(self, title: str, body: str, created_at: str | None = None) -> int:
        ts = now_iso()
        created = created_at or ts
        content_hash = compute_hash(title, body)
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO prompts(title, body, content_hash, created_at, updated_at, is_deleted)
                    VALUES (?, ?, ?, ?, ?, 0)
                    """,
                    (title, body, content_hash, created, ts),
                )
            except IntegrityError as exc:
                raise ValueError("已存在相同标题与正文的提示词") from exc
            return int(cur.lastrowid)

    def get_prompt(self, prompt_id: int) -> PromptRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, title, body, created_at, updated_at, is_deleted FROM prompts WHERE id = ?",
                (prompt_id,),
            ).fetchone()
        if not row:
            return None
        return PromptRecord(**dict(row))

    def list_prompts(self, include_deleted: bool = False) -> list[PromptRecord]:
        sql = "SELECT id, title, body, created_at, updated_at, is_deleted FROM prompts"
        params: tuple[object, ...] = ()
        if not include_deleted:
            sql += " WHERE is_deleted = 0"
        sql += " ORDER BY id ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [PromptRecord(**dict(r)) for r in rows]

    def update_prompt(self, prompt_id: int, title: str | None = None, body: str | None = None) -> bool:
        existing = self.get_prompt(prompt_id)
        if not existing:
            return False
        new_title = title if title is not None else existing.title
        new_body = body if body is not None else existing.body
        with self.connect() as conn:
            try:
                conn.execute(
                    """
                    UPDATE prompts
                    SET title = ?, body = ?, content_hash = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (new_title, new_body, compute_hash(new_title, new_body), now_iso(), prompt_id),
                )
            except IntegrityError as exc:
                raise ValueError("更新后与现有提示词内容重复") from exc
        return True

    def soft_delete(self, prompt_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "UPDATE prompts SET is_deleted = 1, updated_at = ? WHERE id = ?",
                (now_iso(), prompt_id),
            )
        return cur.rowcount > 0

    def ensure_tag(self, name: str) -> int:
        with self.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (name,))
            row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        return int(row["id"])

    def set_tags(self, prompt_id: int, tags: Iterable[str]) -> None:
        with self.connect() as conn:
            for tag in tags:
                conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
                tag_id = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO prompt_tags(prompt_id, tag_id) VALUES (?, ?)",
                    (prompt_id, tag_id),
                )

    def remove_tags(self, prompt_id: int, tags: Iterable[str]) -> None:
        with self.connect() as conn:
            for tag in tags:
                row = conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
                if row:
                    conn.execute(
                        "DELETE FROM prompt_tags WHERE prompt_id = ? AND tag_id = ?",
                        (prompt_id, row["id"]),
                    )

    def get_tags(self, prompt_id: int) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.name
                FROM tags t
                JOIN prompt_tags pt ON pt.tag_id = t.id
                WHERE pt.prompt_id = ?
                ORDER BY t.name ASC
                """,
                (prompt_id,),
            ).fetchall()
        return [str(r["name"]) for r in rows]

    def search(self, query: str, include_deleted: bool = False) -> list[PromptRecord]:
        tokens = tokenize(query)
        if not tokens:
            return []
        where_parts = []
        params: list[object] = []
        for token in tokens:
            where_parts.append(
                "(lower(p.title) LIKE ? OR lower(p.body) LIKE ? OR EXISTS ("
                "SELECT 1 FROM prompt_tags pt JOIN tags t ON t.id = pt.tag_id "
                "WHERE pt.prompt_id = p.id AND lower(t.name) LIKE ?))"
            )
            like = f"%{token}%"
            params.extend([like, like, like])
        sql = "SELECT p.id, p.title, p.body, p.created_at, p.updated_at, p.is_deleted FROM prompts p WHERE "
        sql += " AND ".join(where_parts)
        if not include_deleted:
            sql += " AND p.is_deleted = 0"
        sql += " ORDER BY p.id ASC"
        with self.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [PromptRecord(**dict(r)) for r in rows]

    def get_by_hash(self, content_hash: str) -> PromptRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id, title, body, created_at, updated_at, is_deleted FROM prompts WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        if not row:
            return None
        return PromptRecord(**dict(row))
