import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";
import { app } from "electron";

import { applySchema } from "./schema";

let dbInstance: Database.Database | null = null;

function resolveDbPath(): string {
  const configuredPath = process.env.PROMPT_VAULT_DB_PATH?.trim();
  if (configuredPath) {
    return path.resolve(configuredPath);
  }
  return path.join(app.getPath("userData"), "prompt_vault.sqlite");
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
