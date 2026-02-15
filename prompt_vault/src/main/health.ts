import { app } from "electron";

import { getStorageConfig } from "./db";

export function getHealthPayload() {
  const storage = getStorageConfig();
  return {
    status: "ok" as const,
    mode: "ready" as const,
    appVersion: app.getVersion(),
    dbPath: storage.dbPath,
    storageConfigured: storage.isConfigured,
    storageFolder: storage.selectedFolder,
  };
}
