import { contextBridge, ipcRenderer } from "electron";
import type { IpcRendererEvent } from "electron";

import type {
  ExportJsonInput,
  ExportMarkdownInput,
  MenuCommand,
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
  storage: {
    getConfig: () => invoke("vault:storage:getConfig"),
    chooseFolder: () => invoke("vault:storage:chooseFolder"),
  },
  prompt: {
    list: (input: PromptListInput) => invoke("vault:prompt:list", input),
    get: (promptId: string) => invoke("vault:prompt:get", promptId),
    create: (input: PromptUpsertInput) => invoke("vault:prompt:create", input),
    update: (promptId: string, input: PromptUpsertInput) =>
      invoke("vault:prompt:update", { promptId, input }),
    softDelete: (promptId: string) => invoke("vault:prompt:softDelete", promptId),
    render: (input: PromptRenderInput) => invoke("vault:prompt:render", input),
    copyRendered: (input: PromptRenderInput) => invoke("vault:prompt:copyRendered", input),
    importJson: () => invoke("vault:prompt:importJson"),
    exportJson: (input: ExportJsonInput) => invoke("vault:prompt:exportJson", input),
    exportMarkdown: (input: ExportMarkdownInput) => invoke("vault:prompt:exportMarkdown", input),
  },
  events: {
    onMenuCommand: (listener: (command: MenuCommand) => void) => {
      const wrapped = (_event: IpcRendererEvent, command: MenuCommand) => listener(command);
      ipcRenderer.on("vault:menu-command", wrapped);
      return () => {
        ipcRenderer.removeListener("vault:menu-command", wrapped);
      };
    },
  },
};

contextBridge.exposeInMainWorld("vault", vaultApi);
