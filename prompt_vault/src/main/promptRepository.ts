import { ulid } from "ulid";

import { AppException } from "./appError";
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

type PromptRow = {
  id: string;
  title: string;
  body: string;
  is_deleted: number;
  created_at: string;
  updated_at: string;
};

function normalizeTitle(value: string): string {
  const next = value.trim();
  if (!next) {
    throw new AppException("VALIDATION_ERROR", "标题不能为空");
  }
  return next;
}

function normalizeBody(value: string): string {
  if (!value.trim()) {
    throw new AppException("VALIDATION_ERROR", "正文不能为空");
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

function getTagsByPromptIds(promptIds: string[]): Map<string, string[]> {
  const mapping = new Map<string, string[]>();
  if (promptIds.length === 0) {
    return mapping;
  }

  const db = getDb();
  const placeholders = promptIds.map(() => "?").join(", ");
  const rows = db
    .prepare(
      `
      SELECT prompt_id, tag
      FROM prompt_tags
      WHERE prompt_id IN (${placeholders})
      ORDER BY prompt_id ASC, tag ASC
      `
    )
    .all(...promptIds) as Array<{ prompt_id: string; tag: string }>;

  for (const row of rows) {
    const list = mapping.get(row.prompt_id);
    if (list) {
      list.push(row.tag);
    } else {
      mapping.set(row.prompt_id, [row.tag]);
    }
  }

  return mapping;
}

function mapPromptRow(row: PromptRow, tagsByPromptId: Map<string, string[]>): PromptRecord {
  return {
    id: row.id,
    title: row.title,
    body: row.body,
    tags: tagsByPromptId.get(row.id) ?? [],
    isDeleted: row.is_deleted === 1,
    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function nowIso(): string {
  return new Date().toISOString();
}

function isFtsSyntaxError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const message = error.message.toLowerCase();
  return message.includes("fts5") && message.includes("syntax");
}

function escapeLike(value: string): string {
  return value.replace(/[\\%_]/g, "\\$&");
}

function listFromRows(
  whereClause: string,
  params: Array<string | number>,
  options?: { limit?: number; offset?: number }
): ListPromptOutput {
  const db = getDb();
  const totalRow = db
    .prepare(`SELECT COUNT(*) AS total FROM prompts p ${whereClause}`)
    .get(...params) as { total: number };

  const limitSql = options?.limit !== undefined ? "LIMIT ? OFFSET ?" : "";
  const listParams = [...params];
  if (options?.limit !== undefined) {
    listParams.push(options.limit, options.offset ?? 0);
  }

  const rows = db
    .prepare(
      `
      SELECT p.id, p.title, p.body, p.is_deleted, p.created_at, p.updated_at
      FROM prompts p
      ${whereClause}
      ORDER BY p.updated_at DESC
      ${limitSql}
      `
    )
    .all(...listParams) as PromptRow[];

  const tagsByPromptId = getTagsByPromptIds(rows.map((row) => row.id));

  return {
    total: totalRow.total,
    items: rows.map((row) => mapPromptRow(row, tagsByPromptId)),
  };
}

export function listPrompts(input: ListPromptInput): ListPromptOutput {
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
  try {
    return listFromRows(whereClause, params, { limit, offset });
  } catch (error) {
    if (!query || !isFtsSyntaxError(error)) {
      throw error;
    }
  }

  const like = `%${escapeLike(query)}%`;
  const fallbackWhereParts: string[] = [];
  const fallbackParams: Array<string | number> = [];

  if (!input.includeDeleted) {
    fallbackWhereParts.push("p.is_deleted = 0");
  }

  fallbackWhereParts.push(
    "(" +
      "p.title LIKE ? ESCAPE '\\' COLLATE NOCASE " +
      "OR p.body LIKE ? ESCAPE '\\' COLLATE NOCASE " +
      "OR EXISTS (" +
      "SELECT 1 FROM prompt_tags t WHERE t.prompt_id = p.id AND t.tag LIKE ? ESCAPE '\\' COLLATE NOCASE" +
      ")" +
      ")"
  );
  fallbackParams.push(like, like, like);

  const fallbackWhereClause = `WHERE ${fallbackWhereParts.join(" AND ")}`;
  return listFromRows(fallbackWhereClause, fallbackParams, { limit, offset });
}

export function listAllPrompts(includeDeleted: boolean): PromptRecord[] {
  const whereClause = includeDeleted ? "" : "WHERE p.is_deleted = 0";
  return listFromRows(whereClause, []).items;
}

export function getPrompt(promptId: string): PromptRecord | null {
  const db = getDb();
  const row = db
    .prepare("SELECT id, title, body, is_deleted, created_at, updated_at FROM prompts WHERE id = ?")
    .get(promptId) as PromptRow | undefined;

  if (!row) {
    return null;
  }

  const tagsByPromptId = getTagsByPromptIds([row.id]);
  return mapPromptRow(row, tagsByPromptId);
}

export function promptExistsByTitleBody(title: string, body: string): boolean {
  const db = getDb();
  const row = db
    .prepare("SELECT id FROM prompts WHERE title = ? AND body = ? LIMIT 1")
    .get(title, body) as { id: string } | undefined;
  return Boolean(row);
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
    throw new AppException("NOT_FOUND", "提示词不存在");
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
    throw new AppException("NOT_FOUND", "提示词不存在");
  }
  return prompt.body.replace(PLACEHOLDER, (_match, key: string) => {
    return Object.prototype.hasOwnProperty.call(variables, key) ? variables[key] : `{{${key}}}`;
  });
}
