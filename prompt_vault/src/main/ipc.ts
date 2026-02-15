import { clipboard, dialog, ipcMain } from "electron";
import type { IpcMainInvokeEvent } from "electron";

import type { Result } from "../shared/types";
import { AppException } from "./appError";
import { setStorageFolder, getStorageConfig } from "./db";
import { fail, ok, toAppError } from "./errors";
import { getHealthPayload } from "./health";
import { exportToJson, exportToMarkdown, importFromJson } from "./importExportService";
import {
  normalizeIncludeDeletedPayload,
  normalizePromptId,
  normalizePromptListInput,
  normalizePromptRenderInput,
  normalizePromptUpsertInput,
  normalizeUpdatePayload,
} from "./ipcValidation";
import {
  createPrompt,
  getPrompt,
  listPrompts,
  renderPrompt,
  softDeletePrompt,
  updatePrompt,
} from "./promptRepository";
import { isTrustedSenderUrl } from "./security";

async function safeRun<T>(fn: () => Promise<T> | T): Promise<Result<T>> {
  try {
    return ok(await fn());
  } catch (error) {
    return fail(toAppError(error));
  }
}

function assertTrustedSender(event: IpcMainInvokeEvent): void {
  const senderUrl = event.senderFrame?.url ?? "";
  if (!isTrustedSenderUrl(senderUrl)) {
    throw new AppException("VALIDATION_ERROR", "非法调用来源");
  }
}

function handleTrusted<T>(
  channel: string,
  handler: (event: IpcMainInvokeEvent, payload: unknown) => Promise<T> | T
): void {
  ipcMain.handle(channel, (event, payload) =>
    safeRun(() => {
      assertTrustedSender(event);
      return handler(event, payload);
    })
  );
}

async function pickImportPath(): Promise<string> {
  const result = await dialog.showOpenDialog({
    properties: ["openFile"],
    filters: [{ name: "JSON", extensions: ["json"] }],
  });

  if (result.canceled || result.filePaths.length === 0) {
    throw new AppException("VALIDATION_ERROR", "已取消操作");
  }
  return result.filePaths[0];
}

async function pickExportPath(format: "json" | "markdown"): Promise<string> {
  const ext = format === "markdown" ? "md" : "json";
  const result = await dialog.showSaveDialog({
    filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
  });

  if (result.canceled || !result.filePath) {
    throw new AppException("VALIDATION_ERROR", "已取消操作");
  }
  return result.filePath;
}

async function pickStorageFolder(): Promise<string> {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory", "createDirectory"],
  });

  if (result.canceled || result.filePaths.length === 0) {
    throw new AppException("VALIDATION_ERROR", "已取消操作");
  }

  return result.filePaths[0];
}

export function registerIpcHandlers(): void {
  ipcMain.removeHandler("vault:health");
  ipcMain.removeHandler("vault:storage:getConfig");
  ipcMain.removeHandler("vault:storage:chooseFolder");
  ipcMain.removeHandler("vault:prompt:list");
  ipcMain.removeHandler("vault:prompt:get");
  ipcMain.removeHandler("vault:prompt:create");
  ipcMain.removeHandler("vault:prompt:update");
  ipcMain.removeHandler("vault:prompt:softDelete");
  ipcMain.removeHandler("vault:prompt:render");
  ipcMain.removeHandler("vault:prompt:copyRendered");
  ipcMain.removeHandler("vault:prompt:importJson");
  ipcMain.removeHandler("vault:prompt:exportJson");
  ipcMain.removeHandler("vault:prompt:exportMarkdown");

  handleTrusted("vault:health", () => getHealthPayload());

  handleTrusted("vault:storage:getConfig", () => getStorageConfig());

  handleTrusted("vault:storage:chooseFolder", async () => {
      const folderPath = await pickStorageFolder();
      return setStorageFolder(folderPath);
  });

  handleTrusted("vault:prompt:list", (_event, input) => {
      const normalized = normalizePromptListInput(input);
      return listPrompts(normalized);
  });

  handleTrusted("vault:prompt:get", (_event, promptIdRaw) => {
      const promptId = normalizePromptId(promptIdRaw);
      const prompt = getPrompt(promptId);
      if (!prompt) {
        throw new AppException("NOT_FOUND", "提示词不存在");
      }
      return prompt;
  });

  handleTrusted("vault:prompt:create", (_event, inputRaw) => {
      const input = normalizePromptUpsertInput(inputRaw);
      return createPrompt(input);
  });

  handleTrusted("vault:prompt:update", (_event, payloadRaw) => {
      const payload = normalizeUpdatePayload(payloadRaw);
      return updatePrompt(payload.promptId, payload.input);
  });

  handleTrusted("vault:prompt:softDelete", (_event, promptIdRaw) => {
      const promptId = normalizePromptId(promptIdRaw);
      const deleted = softDeletePrompt(promptId);
      if (!deleted) {
        throw new AppException("NOT_FOUND", "提示词不存在");
      }
      return { deleted: true as const };
  });

  handleTrusted("vault:prompt:render", (_event, inputRaw) => {
      const input = normalizePromptRenderInput(inputRaw);
      const content = renderPrompt(input.promptId, input.variables);
      return { content };
  });

  handleTrusted("vault:prompt:copyRendered", (_event, inputRaw) => {
      const input = normalizePromptRenderInput(inputRaw);
      const content = renderPrompt(input.promptId, input.variables);
      clipboard.writeText(content);
      return { copied: true as const, content };
  });

  handleTrusted("vault:prompt:importJson", async () => {
      const inputPath = await pickImportPath();
      return importFromJson(inputPath);
  });

  handleTrusted("vault:prompt:exportJson", async (_event, payloadRaw) => {
      const { includeDeleted } = normalizeIncludeDeletedPayload(payloadRaw);
      const outputPath = await pickExportPath("json");
      return exportToJson(outputPath, includeDeleted);
  });

  handleTrusted("vault:prompt:exportMarkdown", async (_event, payloadRaw) => {
      const { includeDeleted } = normalizeIncludeDeletedPayload(payloadRaw);
      const outputPath = await pickExportPath("markdown");
      return exportToMarkdown(outputPath, includeDeleted);
  });
}
