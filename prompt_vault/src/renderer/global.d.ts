import type { VaultApi } from "../shared/types";

declare global {
  interface Window {
    vault: VaultApi;
  }
}

export {};
