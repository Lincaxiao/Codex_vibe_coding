import os from "node:os";
import path from "node:path";

import { test, expect, _electron as electron } from "@playwright/test";

test("launch desktop shell", async () => {
  test.skip(!process.env.E2E_RUN, "Set E2E_RUN=1 to run Electron e2e smoke test");

  const app = await electron.launch({
    args: ["."],
    cwd: path.resolve(__dirname, "../.."),
    env: {
      ...process.env,
      PROMPT_VAULT_DB_PATH: path.join(os.tmpdir(), "prompt-vault-e2e.sqlite"),
    },
  });

  const window = await app.firstWindow();
  await expect(window).toHaveTitle(/Prompt Vault/);
  await app.close();
});
