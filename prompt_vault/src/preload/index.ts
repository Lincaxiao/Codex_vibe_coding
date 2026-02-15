import { contextBridge, ipcRenderer } from "electron";

import type {
  ExportJsonInput,
  ExportMarkdownInput,
  ImportJsonInput,
  PromptListInput,
  PromptRenderInput,
  PromptUpsertInput,
  Result,
  VaultApi,
} from "../shared/types";

function invoke<T>(channel: string, payload?: unknown): Promise<Result<T>> {
  return ipcRenderer.invoke(channel, payload) as Promise<Result<T>>;
}

const vaultApi: VaultApi = {
  health: () => invoke("vault:health"),
  prompt: {
    list: (input: PromptListInput) => invoke("vault:prompt:list", input),
    get: (promptId: string) => invoke("vault:prompt:get", promptId),
    create: (input: PromptUpsertInput) => invoke("vault:prompt:create", input),
    update: (promptId: string, input: PromptUpsertInput) =>
      invoke("vault:prompt:update", { promptId, input }),
    softDelete: (promptId: string) => invoke("vault:prompt:softDelete", promptId),
    render: (input: PromptRenderInput) => invoke("vault:prompt:render", input),
    copyRendered: (input: PromptRenderInput) => invoke("vault:prompt:copyRendered", input),
    importJson: (_input: ImportJsonInput) =>
      Promise.resolve({
        ok: false,
        error: { code: "INTERNAL_ERROR", message: "importJson 尚未实现" },
      }),
    exportJson: (_input: ExportJsonInput) =>
      Promise.resolve({
        ok: false,
        error: { code: "INTERNAL_ERROR", message: "exportJson 尚未实现" },
      }),
    exportMarkdown: (_input: ExportMarkdownInput) =>
      Promise.resolve({
        ok: false,
        error: { code: "INTERNAL_ERROR", message: "exportMarkdown 尚未实现" },
      }),
  },
};

contextBridge.exposeInMainWorld("vault", vaultApi);
