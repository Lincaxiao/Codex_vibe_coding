import { describe, expect, test } from "vitest";

import { formatSensitivePath, parseTags, parseVariables } from "../../src/renderer/utils";

describe("renderer/utils", () => {
  test("parseTags deduplicates and trims", () => {
    expect(parseTags(" a, b, a ,\n c ")).toEqual(["a", "b", "c"]);
  });

  test("parseVariables parses key-value pairs", () => {
    expect(parseVariables("name=Alice;date=2026-02-15")).toEqual({
      name: "Alice",
      date: "2026-02-15",
    });
  });

  test("parseVariables throws on invalid token", () => {
    expect(() => parseVariables("invalid-token")).toThrowError();
  });

  test("formatSensitivePath masks absolute paths", () => {
    expect(formatSensitivePath("/Users/alice/Documents/prompt_vault.sqlite")).toBe(
      ".../Documents/prompt_vault.sqlite"
    );
    expect(formatSensitivePath(null)).toBe("未设置");
  });
});
