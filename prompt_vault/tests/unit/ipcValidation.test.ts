import { describe, expect, test } from "vitest";

import { AppException } from "../../src/main/appError";
import {
  normalizeIncludeDeletedPayload,
  normalizePromptListInput,
  normalizePromptRenderInput,
  normalizePromptUpsertInput,
  normalizeUpdatePayload,
} from "../../src/main/ipcValidation";

describe("ipcValidation", () => {
  test("normalizes list input with clamps", () => {
    expect(
      normalizePromptListInput({
        query: "hello",
        includeDeleted: false,
        limit: 999,
        offset: -2,
      })
    ).toEqual({
      query: "hello",
      includeDeleted: false,
      limit: 200,
      offset: 0,
    });
  });

  test("rejects invalid includeDeleted payload", () => {
    expect(() => normalizeIncludeDeletedPayload({ includeDeleted: "yes" })).toThrowError(AppException);
  });

  test("rejects invalid upsert tags", () => {
    expect(() =>
      normalizePromptUpsertInput({
        title: "a",
        body: "b",
        tags: ["ok", 1],
      })
    ).toThrowError(AppException);
  });

  test("normalizes update payload", () => {
    expect(
      normalizeUpdatePayload({
        promptId: "01TEST",
        input: { title: "A", body: "B", tags: ["x"] },
      })
    ).toEqual({
      promptId: "01TEST",
      input: { title: "A", body: "B", tags: ["x"] },
    });
  });

  test("validates render variables", () => {
    expect(
      normalizePromptRenderInput({
        promptId: "01TEST",
        variables: { name: "alice" },
      })
    ).toEqual({
      promptId: "01TEST",
      variables: { name: "alice" },
    });
  });
});
