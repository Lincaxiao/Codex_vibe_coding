import { clipboard, dialog, ipcMain } from "electron";

import type {
  PickExportPathInput,
  PromptListInput,
  PromptRenderInput,
  PromptUpsertInput,
  Result,
} from "../shared/types";
import { fail, ok, toAppError } from "./errors";
import { getHealthPayload } from "./health";
import { exportToJson, exportToMarkdown, importFromJson } from "./importExportService";
import {
  createPrompt,
  getPrompt,
  listPrompts,
  renderPrompt,
  softDeletePrompt,
  updatePrompt,
} from "./promptRepository";

async function safeRun<T>(fn: () => T): Promise<Result<T>> {
  try {
    return ok(fn());
  } catch (error) {
    return fail(toAppError(error));
  }
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
  ipcMain.removeHandler("vault:dialog:pickImportFile");
  ipcMain.removeHandler("vault:dialog:pickExportPath");

  ipcMain.handle("vault:health", () => safeRun(() => getHealthPayload()));

  ipcMain.handle("vault:prompt:list", (_event, input: PromptListInput) =>
    safeRun(() =>
      listPrompts({
        query: input?.query ?? "",
        includeDeleted: Boolean(input?.includeDeleted),
        limit: input?.limit ?? 50,
        offset: input?.offset ?? 0,
      })
    )
  );

  ipcMain.handle("vault:prompt:get", (_event, promptId: string) =>
    safeRun(() => {
      const prompt = getPrompt(promptId);
      if (!prompt) {
        throw new Error("提示词不存在");
      }
      return prompt;
    })
  );

  ipcMain.handle("vault:prompt:create", (_event, input: PromptUpsertInput) =>
    safeRun(() => createPrompt(input))
  );

  ipcMain.handle("vault:prompt:update", (_event, payload: { promptId: string; input: PromptUpsertInput }) =>
    safeRun(() => updatePrompt(payload.promptId, payload.input))
  );

  ipcMain.handle("vault:prompt:softDelete", (_event, promptId: string) =>
    safeRun(() => {
      const deleted = softDeletePrompt(promptId);
      if (!deleted) {
        throw new Error("提示词不存在");
      }
      return { deleted: true as const };
    })
  );

  ipcMain.handle("vault:prompt:render", (_event, input: PromptRenderInput) =>
    safeRun(() => {
      const content = renderPrompt(input.promptId, input.variables);
      return { content };
    })
  );

  ipcMain.handle("vault:prompt:copyRendered", (_event, input: PromptRenderInput) =>
    safeRun(() => {
      const content = renderPrompt(input.promptId, input.variables);
      clipboard.writeText(content);
      return { copied: true as const, content };
    })
  );

  ipcMain.handle("vault:prompt:importJson", (_event, payload: { inputPath: string }) =>
    safeRun(() => importFromJson(payload.inputPath))
  );

  ipcMain.handle(
    "vault:prompt:exportJson",
    (_event, payload: { outputPath: string; includeDeleted: boolean }) =>
      safeRun(() => exportToJson(payload.outputPath, payload.includeDeleted))
  );

  ipcMain.handle(
    "vault:prompt:exportMarkdown",
    (_event, payload: { outputPath: string; includeDeleted: boolean }) =>
      safeRun(() => exportToMarkdown(payload.outputPath, payload.includeDeleted))
  );

  ipcMain.handle("vault:dialog:pickImportFile", () =>
    safeRun(() => {
      const result = dialog.showOpenDialogSync({
        properties: ["openFile"],
        filters: [{ name: "JSON", extensions: ["json"] }],
      });

      if (!result || result.length === 0) {
        throw new Error("已取消操作");
      }
      return { path: result[0] };
    })
  );

  ipcMain.handle("vault:dialog:pickExportPath", (_event, input: PickExportPathInput) =>
    safeRun(() => {
      const ext = input.format === "markdown" ? "md" : "json";
      const result = dialog.showSaveDialogSync({
        defaultPath: input.defaultPath,
        filters: [{ name: ext.toUpperCase(), extensions: [ext] }],
      });

      if (!result) {
        throw new Error("已取消操作");
      }
      return { path: result };
    })
  );
}
