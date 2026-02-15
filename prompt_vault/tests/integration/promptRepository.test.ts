import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { beforeEach, describe, expect, test } from "vitest";

import { closeDb } from "../../src/main/db";
import { exportToJson, importFromJson } from "../../src/main/importExportService";
import {
  createPrompt,
  getPrompt,
  listAllPrompts,
  listPrompts,
  renderPrompt,
  softDeletePrompt,
  updatePrompt,
} from "../../src/main/promptRepository";

const workspace = path.join(os.tmpdir(), "prompt-vault-tests");

function prepareDb(name: string) {
  closeDb();
  fs.mkdirSync(workspace, { recursive: true });
  process.env.PROMPT_VAULT_DB_PATH = path.join(workspace, `${name}.sqlite`);
}

beforeEach(() => {
  closeDb();
  fs.rmSync(workspace, { recursive: true, force: true });
  fs.mkdirSync(workspace, { recursive: true });
});

describe("promptRepository integration", () => {
  test("CRUD flow with soft delete", () => {
    prepareDb("crud");

    const created = createPrompt({
      title: "Lecture 1",
      body: "content {{name}}",
      tags: ["ml", "intro"],
    });

    const loaded = getPrompt(created.id);
    expect(loaded?.title).toBe("Lecture 1");

    const updated = updatePrompt(created.id, {
      title: "Lecture 1 Updated",
      body: "new body",
      tags: ["ml", "updated"],
    });
    expect(updated.tags).toEqual(["ml", "updated"]);

    expect(softDeletePrompt(created.id)).toBe(true);

    expect(listPrompts({ query: "", includeDeleted: false, limit: 20, offset: 0 }).items).toHaveLength(0);
    expect(listPrompts({ query: "", includeDeleted: true, limit: 20, offset: 0 }).items).toHaveLength(1);
  });

  test("FTS search includes tags", () => {
    prepareDb("search");

    createPrompt({
      title: "Prompt A",
      body: "this is first body",
      tags: ["networking"],
    });
    createPrompt({
      title: "Prompt B",
      body: "another body",
      tags: ["database"],
    });

    const hits = listPrompts({ query: "networking", includeDeleted: true, limit: 20, offset: 0 });
    expect(hits.total).toBe(1);
    expect(hits.items[0]?.title).toBe("Prompt A");
  });

  test("renderPrompt replaces variables", () => {
    prepareDb("render");

    const created = createPrompt({
      title: "Render",
      body: "hello {{name}}",
      tags: [],
    });

    const content = renderPrompt(created.id, { name: "World" });
    expect(content).toBe("hello World");
  });

  test("import/export roundtrip", async () => {
    prepareDb("export_src");

    createPrompt({ title: "A", body: "Body A", tags: ["a"] });
    createPrompt({ title: "B", body: "Body B", tags: ["b"] });

    const jsonPath = path.join(workspace, "prompts.json");
    await exportToJson(jsonPath, true);
    expect(fs.existsSync(jsonPath)).toBe(true);

    prepareDb("import_target");
    const result = await importFromJson(jsonPath);
    expect(result.added).toBe(2);
    expect(listAllPrompts(true)).toHaveLength(2);
  });
});
