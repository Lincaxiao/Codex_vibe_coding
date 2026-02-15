import { clipboard, ipcMain } from "electron";

import type {
  PromptListInput,
  PromptRenderInput,
  PromptUpsertInput,
  Result,
  VaultApi,
} from "../shared/types";
import { fail, ok, toAppError } from "./errors";
import { getHealthPayload } from "./health";
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
}

export const _typeGuard: VaultApi | null = null;
