import type Database from "better-sqlite3";

export function applySchema(db: Database.Database): void {
  db.pragma("foreign_keys = ON");
  db.exec(`
    CREATE TABLE IF NOT EXISTS prompts (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS prompt_tags (
      prompt_id TEXT NOT NULL,
      tag TEXT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY (prompt_id, tag),
      FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_prompt_tags_tag ON prompt_tags(tag);

    CREATE VIRTUAL TABLE IF NOT EXISTS prompt_fts USING fts5(
      prompt_id UNINDEXED,
      title,
      body,
      tags_text
    );
  `);
}
