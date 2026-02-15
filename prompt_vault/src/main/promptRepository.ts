import { ulid } from "ulid";

import { getDb } from "./db";

export type PromptRecord = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  isDeleted: boolean;
  createdAt: string;
  updatedAt: string;
};

export type ListPromptInput = {
  query: string;
  includeDeleted: boolean;
  limit: number;
  offset: number;
};

export type ListPromptOutput = {
  items: PromptRecord[];
  total: number;
};

export type PromptUpsertInput = {
  title: string;
  body: string;
  tags: string[];
};

function normalizeTitle(value: string): string {
  const next = value.trim();
  if (!next) {
    throw new Error("标题不能为空");
  }
  return next;
}

function normalizeBody(value: string): string {
  if (!value.trim()) {
    throw new Error("正文不能为空");
  }
  return value;
}

function normalizeTags(value: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const raw of value) {
    const tag = raw.trim();
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    result.push(tag);
  }

  return result;
}

function refreshFtsRow(promptId: string): void {
  const db = getDb();
  db.prepare("DELETE FROM prompt_fts WHERE prompt_id = ?").run(promptId);

  const row = db
    .prepare(
      `
      SELECT p.id, p.title, p.body,
             COALESCE(GROUP_CONCAT(t.tag, ' '), '') AS tags_text
      FROM prompts p
      LEFT JOIN prompt_tags t ON t.prompt_id = p.id
      WHERE p.id = ?
      GROUP BY p.id
      `
    )
    .get(promptId) as { id: string; title: string; body: string; tags_text: string } | undefined;

  if (!row) {
    return;
  }

  db.prepare("INSERT INTO prompt_fts(prompt_id, title, body, tags_text) VALUES (?, ?, ?, ?)").run(
    row.id,
    row.title,
    row.body,
    row.tags_text
  );
}

function mapPromptRow(row: {
  id: string;
  title: string;
  body: string;
  is_deleted: number;
  created_at: string;
  updated_at: string;
}): PromptRecord {
  const db = getDb();
  const tags = db
    .prepare("SELECT tag FROM prompt_tags WHERE prompt_id = ? ORDER BY tag ASC")
    .all(row.id) as Array<{ tag: string }>;

  return {
    id: row.id,
    title: row.title,
    body: row.body,
    tags: tags.map((item) => item.tag),
    isDeleted: row.is_deleted === 1,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function nowIso(): string {
  return new Date().toISOString();
}

export function listPrompts(input: ListPromptInput): ListPromptOutput {
  const db = getDb();
  const query = input.query.trim();
  const limit = Math.max(1, Math.min(input.limit, 200));
  const offset = Math.max(0, input.offset);

  const whereParts: string[] = [];
  const params: Array<string | number> = [];

  if (!input.includeDeleted) {
    whereParts.push("p.is_deleted = 0");
  }

  if (query) {
    whereParts.push("p.id IN (SELECT prompt_id FROM prompt_fts WHERE prompt_fts MATCH ?)");
    params.push(query);
  }

  const whereClause = whereParts.length ? `WHERE ${whereParts.join(" AND ")}` : "";

  const totalRow = db
    .prepare(`SELECT COUNT(*) AS total FROM prompts p ${whereClause}`)
    .get(...params) as { total: number };

  const items = db
    .prepare(
      `
      SELECT p.id, p.title, p.body, p.is_deleted, p.created_at, p.updated_at
      FROM prompts p
      ${whereClause}
      ORDER BY p.updated_at DESC
      LIMIT ? OFFSET ?
      `
    )
    .all(...params, limit, offset) as Array<{
    id: string;
    title: string;
    body: string;
    is_deleted: number;
    created_at: string;
    updated_at: string;
  }>;

  return {
    total: totalRow.total,
    items: items.map(mapPromptRow),
  };
}

export function getPrompt(promptId: string): PromptRecord | null {
  const db = getDb();
  const row = db
    .prepare(
      "SELECT id, title, body, is_deleted, created_at, updated_at FROM prompts WHERE id = ?"
    )
    .get(promptId) as {
    id: string;
    title: string;
    body: string;
    is_deleted: number;
    created_at: string;
    updated_at: string;
  } | undefined;

  if (!row) {
    return null;
  }
  return mapPromptRow(row);
}

export function createPrompt(input: PromptUpsertInput): PromptRecord {
  const db = getDb();
  const id = ulid();
  const title = normalizeTitle(input.title);
  const body = normalizeBody(input.body);
  const tags = normalizeTags(input.tags);
  const ts = nowIso();

  const tx = db.transaction(() => {
    db.prepare(
      "INSERT INTO prompts(id, title, body, is_deleted, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)"
    ).run(id, title, body, ts, ts);

    const tagStmt = db.prepare(
      "INSERT INTO prompt_tags(prompt_id, tag, created_at) VALUES (?, ?, ?) ON CONFLICT(prompt_id, tag) DO NOTHING"
    );
    for (const tag of tags) {
      tagStmt.run(id, tag, ts);
    }

    refreshFtsRow(id);
  });

  tx();
  return getPrompt(id)!;
}

export function updatePrompt(promptId: string, input: PromptUpsertInput): PromptRecord {
  const db = getDb();
  const existing = getPrompt(promptId);
  if (!existing) {
    throw new Error("提示词不存在");
  }

  const title = normalizeTitle(input.title);
  const body = normalizeBody(input.body);
  const tags = normalizeTags(input.tags);
  const ts = nowIso();

  const tx = db.transaction(() => {
    db.prepare("UPDATE prompts SET title = ?, body = ?, updated_at = ? WHERE id = ?").run(
      title,
      body,
      ts,
      promptId
    );

    db.prepare("DELETE FROM prompt_tags WHERE prompt_id = ?").run(promptId);
    const tagStmt = db.prepare("INSERT INTO prompt_tags(prompt_id, tag, created_at) VALUES (?, ?, ?)");
    for (const tag of tags) {
      tagStmt.run(promptId, tag, ts);
    }

    refreshFtsRow(promptId);
  });

  tx();
  return getPrompt(promptId)!;
}

export function softDeletePrompt(promptId: string): boolean {
  const db = getDb();
  const result = db.prepare("UPDATE prompts SET is_deleted = 1, updated_at = ? WHERE id = ?").run(nowIso(), promptId);
  if (result.changes > 0) {
    refreshFtsRow(promptId);
    return true;
  }
  return false;
}

const PLACEHOLDER = /\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}/g;

export function renderPrompt(promptId: string, variables: Record<string, string>): string {
  const prompt = getPrompt(promptId);
  if (!prompt) {
    throw new Error("提示词不存在");
  }
  return prompt.body.replace(PLACEHOLDER, (_match, key: string) => {
    return Object.prototype.hasOwnProperty.call(variables, key) ? variables[key] : `{{${key}}}`;
  });
}
