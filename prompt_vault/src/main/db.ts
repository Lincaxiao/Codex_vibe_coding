import fs from "node:fs";
import path from "node:path";

import Database from "better-sqlite3";

import { AppException } from "./appError";
import { toPathLabel } from "./pathMask";
import { applySchema } from "./schema";
import { readStorageDirectoryState, saveStorageDirectory } from "./storageSettings";

let dbInstance: Database.Database | null = null;

export type StorageConfig = {
  isConfigured: boolean;
  selectedFolder: string | null;
  dbPath: string | null;
  source: "env" | "user_selected" | "unset" | "corrupted";
  warning: string | null;
};

function resolveEnvDbPath(): string | null {
  const configuredPath = process.env.PROMPT_VAULT_DB_PATH?.trim();
  if (!configuredPath) {
    return null;
  }
  return path.resolve(configuredPath);
}

function resolveDbPath(): string {
  const envDbPath = resolveEnvDbPath();
  if (envDbPath) {
    return envDbPath;
  }

  const storage = readStorageDirectoryState();
  if (storage.directory) {
    return path.join(storage.directory, "prompt_vault.sqlite");
  }

  if (storage.corrupted) {
    throw new AppException("VALIDATION_ERROR", "存储配置损坏，请重新选择数据存储文件夹");
  }

  throw new AppException("VALIDATION_ERROR", "请先在“存储位置”里选择数据存储文件夹");
}

export function getStorageConfig(): StorageConfig {
  const envDbPath = resolveEnvDbPath();
  if (envDbPath) {
    return {
      isConfigured: true,
      selectedFolder: toPathLabel(path.dirname(envDbPath)),
      dbPath: toPathLabel(envDbPath),
      source: "env",
      warning: null,
    };
  }

  const storage = readStorageDirectoryState();
  if (!storage.directory) {
    if (storage.corrupted) {
      return {
        isConfigured: false,
        selectedFolder: null,
        dbPath: null,
        source: "corrupted",
        warning: "存储配置文件已损坏，请重新选择数据存储文件夹",
      };
    }

    return {
      isConfigured: false,
      selectedFolder: null,
      dbPath: null,
      source: "unset",
      warning: null,
    };
  }

  return {
    isConfigured: true,
    selectedFolder: toPathLabel(storage.directory),
    dbPath: "prompt_vault.sqlite",
    source: "user_selected",
    warning: null,
  };
}

export function setStorageFolder(folderPath: string): StorageConfig {
  if (resolveEnvDbPath()) {
    throw new AppException("VALIDATION_ERROR", "当前数据库路径由环境变量锁定，无法在界面中修改");
  }

  const selectedFolder = saveStorageDirectory(folderPath);
  closeDb();

  return {
    isConfigured: true,
    selectedFolder: toPathLabel(selectedFolder),
    dbPath: "prompt_vault.sqlite",
    source: "user_selected",
    warning: null,
  };
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
