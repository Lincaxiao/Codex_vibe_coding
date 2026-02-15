import { clipboard, dialog, ipcMain } from "electron";

import type { Result } from "../shared/types";
import { AppException } from "./appError";
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

async function safeRun<T>(fn: () => Promise<T> | T): Promise<Result<T>> {
  try {
    return ok(await fn());
  } catch (error) {
    return fail(toAppError(error));
  }
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

export function registerIpcHandlers(): void {
  ipcMain.removeHandler("vault:health");
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

  ipcMain.handle("vault:health", () => safeRun(() => getHealthPayload()));

  ipcMain.handle("vault:prompt:list", (_event, input: unknown) =>
    safeRun(() => {
      const normalized = normalizePromptListInput(input);
      return listPrompts(normalized);
    })
  );

  ipcMain.handle("vault:prompt:get", (_event, promptIdRaw: unknown) =>
    safeRun(() => {
      const promptId = normalizePromptId(promptIdRaw);
      const prompt = getPrompt(promptId);
      if (!prompt) {
        throw new AppException("NOT_FOUND", "提示词不存在");
      }
      return prompt;
    })
  );

  ipcMain.handle("vault:prompt:create", (_event, inputRaw: unknown) =>
    safeRun(() => {
      const input = normalizePromptUpsertInput(inputRaw);
      return createPrompt(input);
    })
  );

  ipcMain.handle("vault:prompt:update", (_event, payloadRaw: unknown) =>
    safeRun(() => {
      const payload = normalizeUpdatePayload(payloadRaw);
      return updatePrompt(payload.promptId, payload.input);
    })
  );

  ipcMain.handle("vault:prompt:softDelete", (_event, promptIdRaw: unknown) =>
    safeRun(() => {
      const promptId = normalizePromptId(promptIdRaw);
      const deleted = softDeletePrompt(promptId);
      if (!deleted) {
        throw new AppException("NOT_FOUND", "提示词不存在");
      }
      return { deleted: true as const };
    })
  );

  ipcMain.handle("vault:prompt:render", (_event, inputRaw: unknown) =>
    safeRun(() => {
      const input = normalizePromptRenderInput(inputRaw);
      const content = renderPrompt(input.promptId, input.variables);
      return { content };
    })
  );

  ipcMain.handle("vault:prompt:copyRendered", (_event, inputRaw: unknown) =>
    safeRun(() => {
      const input = normalizePromptRenderInput(inputRaw);
      const content = renderPrompt(input.promptId, input.variables);
      clipboard.writeText(content);
      return { copied: true as const, content };
    })
  );

  ipcMain.handle("vault:prompt:importJson", () =>
    safeRun(async () => {
      const inputPath = await pickImportPath();
      return importFromJson(inputPath);
    })
  );

  ipcMain.handle("vault:prompt:exportJson", (_event, payloadRaw: unknown) =>
    safeRun(async () => {
      const { includeDeleted } = normalizeIncludeDeletedPayload(payloadRaw);
      const outputPath = await pickExportPath("json");
      return exportToJson(outputPath, includeDeleted);
    })
  );

  ipcMain.handle("vault:prompt:exportMarkdown", (_event, payloadRaw: unknown) =>
    safeRun(async () => {
      const { includeDeleted } = normalizeIncludeDeletedPayload(payloadRaw);
      const outputPath = await pickExportPath("markdown");
      return exportToMarkdown(outputPath, includeDeleted);
    })
  );
}
