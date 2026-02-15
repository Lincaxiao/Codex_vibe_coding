import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";

import { applySchema } from "./schema";

let dbInstance: Database.Database | null = null;

function resolveDbPath(): string {
  const configuredPath = process.env.PROMPT_VAULT_DB_PATH?.trim();
  if (configuredPath) {
    return path.resolve(configuredPath);
  }

  try {
    // Use runtime require to keep integration tests executable in a plain Node process.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const electron = require("electron") as { app?: { getPath: (name: string) => string } };
    if (electron.app?.getPath) {
      return path.join(electron.app.getPath("userData"), "prompt_vault.sqlite");
    }
  } catch {
    // ignored on non-electron process
  }

  throw new Error("未找到数据库路径，请设置 PROMPT_VAULT_DB_PATH");
}

export function getDb(): Database.Database {
  if (dbInstance) {
    return dbInstance;
  }

  const dbPath = resolveDbPath();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  dbInstance = new Database(dbPath);
  applySchema(dbInstance);
  return dbInstance;
}

export function closeDb(): void {
  if (!dbInstance) {
    return;
  }
  dbInstance.close();
  dbInstance = null;
}

export function getDbPath(): string {
  return resolveDbPath();
}
