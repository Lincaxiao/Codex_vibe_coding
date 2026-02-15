import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { readStorageDirectoryState, saveStorageDirectory } from "../../src/main/storageSettings";

const tempRoot = path.join(os.tmpdir(), "prompt-vault-storage-settings-tests");
const settingsPath = path.join(tempRoot, "storage_settings.json");

beforeEach(() => {
  fs.rmSync(tempRoot, { recursive: true, force: true });
  fs.mkdirSync(tempRoot, { recursive: true });
  process.env.PROMPT_VAULT_SETTINGS_PATH = settingsPath;
});

afterEach(() => {
  delete process.env.PROMPT_VAULT_SETTINGS_PATH;
  fs.rmSync(tempRoot, { recursive: true, force: true });
});

describe("storageSettings", () => {
  test("returns unconfigured when settings file does not exist", () => {
    expect(readStorageDirectoryState()).toEqual({
      directory: null,
      corrupted: false,
    });
  });

  test("returns corrupted for invalid settings json", () => {
    fs.writeFileSync(settingsPath, "{ invalid", "utf-8");

    expect(readStorageDirectoryState()).toEqual({
      directory: null,
      corrupted: true,
    });
  });

  test("reads saved storage directory", () => {
    const folder = path.join(tempRoot, "vault-data");
    saveStorageDirectory(folder);

    expect(readStorageDirectoryState()).toEqual({
      directory: folder,
      corrupted: false,
    });
  });
});
