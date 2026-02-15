import type { HealthPayload } from "../shared/types";

declare global {
  interface Window {
    vault: {
      health: () => Promise<HealthPayload>;
    };
  }
}

export {};
