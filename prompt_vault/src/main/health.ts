import { app } from "electron";

import { getDbPath } from "./db";

export function getHealthPayload() {
  return {
    status: "ok" as const,
    mode: "ready" as const,
    appVersion: app.getVersion(),
    dbPath: getDbPath(),
  };
}
