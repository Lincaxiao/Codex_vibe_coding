import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("vault", {
  health: async () => ({ status: "ok", mode: "skeleton" as const }),
});
