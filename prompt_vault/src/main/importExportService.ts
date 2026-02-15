import fs from "node:fs";
import path from "node:path";

import {
  createPrompt,
  listAllPrompts,
  promptExistsByTitleBody,
  softDeletePrompt,
} from "./promptRepository";

type ImportItem = {
  title?: unknown;
  body?: unknown;
  tags?: unknown;
  is_deleted?: unknown;
  isDeleted?: unknown;
};

function ensureDir(filePath: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

export function importFromJson(inputPath: string): { added: number; skipped: number } {
  const raw = fs.readFileSync(inputPath, "utf-8");
  let payload: unknown;

  try {
    payload = JSON.parse(raw);
  } catch {
    throw new Error("IMPORT_FORMAT_ERROR: JSON 解析失败");
  }

  if (!Array.isArray(payload)) {
    throw new Error("IMPORT_FORMAT_ERROR: 导入文件必须是数组");
  }

  let added = 0;
  let skipped = 0;

  for (const item of payload) {
    const row = item as ImportItem;
    const title = typeof row.title === "string" ? row.title.trim() : "";
    const body = typeof row.body === "string" ? row.body : "";

    if (!title || !body.trim()) {
      skipped += 1;
      continue;
    }

    if (promptExistsByTitleBody(title, body)) {
      skipped += 1;
      continue;
    }

    const tags = Array.isArray(row.tags)
      ? row.tags.map((tag) => String(tag)).filter((tag) => tag.trim().length > 0)
      : [];

    const created = createPrompt({
      title,
      body,
      tags,
    });

    if (row.is_deleted === true || row.isDeleted === true) {
      softDeletePrompt(created.id);
    }

    added += 1;
  }

  return { added, skipped };
}

export function exportToJson(outputPath: string, includeDeleted: boolean): { outputPath: string } {
  const prompts = listAllPrompts(includeDeleted).map((item) => ({
    id: item.id,
    title: item.title,
    body: item.body,
    tags: item.tags,
    is_deleted: item.isDeleted,
    created_at: item.createdAt,
    updated_at: item.updatedAt,
  }));

  ensureDir(outputPath);
  fs.writeFileSync(outputPath, `${JSON.stringify(prompts, null, 2)}\n`, "utf-8");
  return { outputPath };
}

export function exportToMarkdown(outputPath: string, includeDeleted: boolean): { outputPath: string } {
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

  ensureDir(outputPath);
  fs.writeFileSync(outputPath, `${lines.join("\n")}\n`, "utf-8");
  return { outputPath };
}
