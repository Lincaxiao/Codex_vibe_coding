import path from "node:path";
import { app, BrowserWindow } from "electron";

import { closeDb } from "./db";
import { registerIpcHandlers } from "./ipc";
import { installAppMenu } from "./menu";
import { isAllowedDevServerUrl } from "./security";

function resolveDevServerUrl(): string | null {
  const rawUrl = process.env.PROMPT_VAULT_DEV_SERVER_URL?.trim();
  if (!rawUrl) {
    return null;
  }

  if (app.isPackaged) {
    return null;
  }

  if (!isAllowedDevServerUrl(rawUrl)) {
    throw new Error("PROMPT_VAULT_DEV_SERVER_URL 仅允许 http://127.0.0.1:5173");
  }

  return rawUrl;
}

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1240,
    height: 860,
    minWidth: 1080,
    minHeight: 720,
    title: "Prompt Vault",
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const devUrl = resolveDevServerUrl();
  if (devUrl) {
    void window.loadURL(devUrl);
    window.webContents.openDevTools({ mode: "detach" });
  } else {
    const indexHtml = path.join(__dirname, "../../dist/renderer/index.html");
    void window.loadFile(indexHtml);
  }
  return window;
}

app.whenReady().then(() => {
  registerIpcHandlers();
  installAppMenu();
  createMainWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  closeDb();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  closeDb();
});
