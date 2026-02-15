import fs from "node:fs";
import path from "node:path";

import { AppException } from "./appError";

type StorageSettingsPayload = {
  dbDirectory: string;
};

export type StorageReadResult = {
  directory: string | null;
  corrupted: boolean;
};

function resolveSettingsPath(): string {
  const configuredPath = process.env.PROMPT_VAULT_SETTINGS_PATH?.trim();
  if (configuredPath) {
    return path.resolve(configuredPath);
  }

  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const electron = require("electron") as { app?: { getPath: (name: string) => string } };
    if (electron.app?.getPath) {
      return path.join(electron.app.getPath("userData"), "storage_settings.json");
    }
  } catch {
    // ignored
  }

  throw new AppException("INTERNAL_ERROR", "无法定位存储设置文件");
}

export function readStorageDirectoryState(): StorageReadResult {
  const settingsPath = resolveSettingsPath();
  if (!fs.existsSync(settingsPath)) {
    return {
      directory: null,
      corrupted: false,
    };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(fs.readFileSync(settingsPath, "utf-8"));
  } catch {
    return {
      directory: null,
      corrupted: true,
    };
  }

  if (!payload || typeof payload !== "object") {
    return {
      directory: null,
      corrupted: true,
    };
  }

  const value = (payload as Partial<StorageSettingsPayload>).dbDirectory;
  if (typeof value !== "string" || !value.trim()) {
    return {
      directory: null,
      corrupted: true,
    };
  }

  return {
    directory: path.resolve(value),
    corrupted: false,
  };
}

export function readStorageDirectory(): string | null {
  return readStorageDirectoryState().directory;
}

export function saveStorageDirectory(folderPath: string): string {
  const normalized = folderPath.trim();
  if (!normalized) {
    throw new AppException("VALIDATION_ERROR", "存储文件夹不能为空");
  }

  const absolutePath = path.resolve(normalized);
  fs.mkdirSync(absolutePath, { recursive: true });

  const settingsPath = resolveSettingsPath();
  fs.mkdirSync(path.dirname(settingsPath), { recursive: true });
  fs.writeFileSync(
    settingsPath,
    `${JSON.stringify({ dbDirectory: absolutePath }, null, 2)}\n`,
    "utf-8"
  );

  return absolutePath;
}
