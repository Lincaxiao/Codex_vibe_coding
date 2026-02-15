import fs from "node:fs/promises";
import path from "node:path";
import { ulid } from "ulid";

import { AppException } from "./appError";
import { getDb } from "./db";
import { toPathLabel } from "./pathMask";
import { listAllPrompts } from "./promptRepository";

type ImportItem = {
  title?: unknown;
  body?: unknown;
  tags?: unknown;
  is_deleted?: unknown;
  isDeleted?: unknown;
};

type ImportFailure = {
  index: number;
  reason: string;
};

type NormalizedImportPrompt = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  isDeleted: boolean;
  createdAt: string;
  updatedAt: string;
};

async function ensureDir(filePath: string): Promise<void> {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

function uniqueNormalizedTags(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  const seen = new Set<string>();
  const tags: string[] = [];
  for (const candidate of raw) {
    const tag = String(candidate).trim();
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

function loadExistingTitleBodySet(): Set<string> {
  const db = getDb();
  const rows = db.prepare("SELECT title, body FROM prompts").all() as Array<{ title: string; body: string }>;
  return new Set(rows.map((row) => `${row.title}\u0000${row.body}`));
}

function validateImportPayload(payload: unknown[]): {
  prompts: NormalizedImportPrompt[];
  skipped: number;
  failures: ImportFailure[];
} {
  const prompts: NormalizedImportPrompt[] = [];
  const failures: ImportFailure[] = [];
  const existing = loadExistingTitleBodySet();
  const withinFile = new Set<string>();
  let skipped = 0;

  for (const [index, item] of payload.entries()) {
    const row = item as ImportItem;
    const title = typeof row.title === "string" ? row.title.trim() : "";
    const body = typeof row.body === "string" ? row.body : "";

    if (!title) {
      skipped += 1;
      failures.push({ index, reason: "标题为空或格式错误" });
      continue;
    }

    if (!body.trim()) {
      skipped += 1;
      failures.push({ index, reason: "正文为空或格式错误" });
      continue;
    }

    const dedupeKey = `${title}\u0000${body}`;
    if (existing.has(dedupeKey) || withinFile.has(dedupeKey)) {
      skipped += 1;
      failures.push({ index, reason: "已存在相同标题和正文，已跳过" });
      continue;
    }

    withinFile.add(dedupeKey);
    const now = new Date().toISOString();
    prompts.push({
      id: ulid(),
      title,
      body,
      tags: uniqueNormalizedTags(row.tags),
      isDeleted: row.is_deleted === true || row.isDeleted === true,
      createdAt: now,
      updatedAt: now,
    });
  }

  return { prompts, skipped, failures };
}

function insertPromptsAtomic(prompts: NormalizedImportPrompt[]): void {
  if (prompts.length === 0) {
    return;
  }

  const db = getDb();
  const insertPrompt = db.prepare(
    "INSERT INTO prompts(id, title, body, is_deleted, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)"
  );
  const insertTag = db.prepare(
    "INSERT INTO prompt_tags(prompt_id, tag, created_at) VALUES (?, ?, ?) ON CONFLICT(prompt_id, tag) DO NOTHING"
  );
  const deleteFts = db.prepare("DELETE FROM prompt_fts WHERE prompt_id = ?");
  const insertFts = db.prepare(
    "INSERT INTO prompt_fts(prompt_id, title, body, tags_text) VALUES (?, ?, ?, ?)"
  );

  const tx = db.transaction((rows: NormalizedImportPrompt[]) => {
    for (const row of rows) {
      insertPrompt.run(row.id, row.title, row.body, row.isDeleted ? 1 : 0, row.createdAt, row.updatedAt);
      for (const tag of row.tags) {
        insertTag.run(row.id, tag, row.createdAt);
      }
      deleteFts.run(row.id);
      insertFts.run(row.id, row.title, row.body, row.tags.join(" "));
    }
  });

  tx(prompts);
}

export async function importFromJson(inputPath: string): Promise<{
  added: number;
  skipped: number;
  sourcePath: string;
  failures: ImportFailure[];
}> {
  let raw = "";
  try {
    raw = await fs.readFile(inputPath, "utf-8");
  } catch {
    throw new AppException("IO_ERROR", "读取导入文件失败");
  }

  let payload: unknown;

  try {
    payload = JSON.parse(raw);
  } catch {
    throw new AppException("IMPORT_FORMAT_ERROR", "JSON 解析失败");
  }

  if (!Array.isArray(payload)) {
    throw new AppException("IMPORT_FORMAT_ERROR", "导入文件必须是数组");
  }

  const { prompts, skipped, failures } = validateImportPayload(payload);
  try {
    insertPromptsAtomic(prompts);
  } catch {
    throw new AppException("DB_ERROR", "导入失败，未写入任何数据");
  }

  return {
    added: prompts.length,
    skipped,
    sourcePath: toPathLabel(inputPath),
    failures,
  };
}

export async function exportToJson(
  outputPath: string,
  includeDeleted: boolean
): Promise<{ outputPath: string }> {
  const prompts = listAllPrompts(includeDeleted).map((item) => ({
    id: item.id,
    title: item.title,
    body: item.body,
    tags: item.tags,
    is_deleted: item.isDeleted,
    created_at: item.createdAt,
    updated_at: item.updatedAt,
  }));

  try {
    await ensureDir(outputPath);
    await fs.writeFile(outputPath, `${JSON.stringify(prompts, null, 2)}\n`, "utf-8");
  } catch {
    throw new AppException("IO_ERROR", "导出 JSON 失败");
  }

  return { outputPath: toPathLabel(outputPath) };
}

export async function exportToMarkdown(
  outputPath: string,
  includeDeleted: boolean
): Promise<{ outputPath: string }> {
  const prompts = listAllPrompts(includeDeleted);
  const lines: string[] = ["# Prompt Vault 导出", ""];

  for (const prompt of prompts) {
    lines.push(`## [${prompt.id}] ${prompt.title}`);
    lines.push(`- 创建时间: ${prompt.createdAt}`);
    lines.push(`- 更新时间: ${prompt.updatedAt}`);
    lines.push(`- 已删除: ${prompt.isDeleted}`);
    lines.push(`- 标签: ${prompt.tags.join(", ") || "(无标签)"}`);
    lines.push("");
    lines.push("```text");
    lines.push(prompt.body);
    lines.push("```");
    lines.push("");
  }

  try {
    await ensureDir(outputPath);
    await fs.writeFile(outputPath, `${lines.join("\n")}\n`, "utf-8");
  } catch {
    throw new AppException("IO_ERROR", "导出 Markdown 失败");
  }

  return { outputPath: toPathLabel(outputPath) };
}
