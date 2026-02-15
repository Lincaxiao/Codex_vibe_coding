import { describe, expect, test } from "vitest";

import { isAllowedDevServerUrl, isTrustedSenderUrl } from "../../src/main/security";

describe("security", () => {
  test("allows only strict local dev url", () => {
    expect(isAllowedDevServerUrl("http://127.0.0.1:5173")).toBe(true);
    expect(isAllowedDevServerUrl("http://127.0.0.1:5173/")).toBe(true);

    expect(isAllowedDevServerUrl("http://localhost:5173")).toBe(false);
    expect(isAllowedDevServerUrl("https://127.0.0.1:5173")).toBe(false);
    expect(isAllowedDevServerUrl("http://127.0.0.1:3000")).toBe(false);
  });

  test("trusted sender url supports file and strict local dev", () => {
    expect(isTrustedSenderUrl("file:///Users/demo/index.html")).toBe(true);
    expect(isTrustedSenderUrl("http://127.0.0.1:5173")).toBe(true);
    expect(isTrustedSenderUrl("https://example.com")).toBe(false);
  });
});
