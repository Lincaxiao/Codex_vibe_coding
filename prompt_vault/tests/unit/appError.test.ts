import { describe, expect, test } from "vitest";

import { asAppError, AppException } from "../../src/main/appError";

describe("appError", () => {
  test("maps AppException with explicit code", () => {
    const error = asAppError(new AppException("NOT_FOUND", "missing"));
    expect(error).toEqual({ code: "NOT_FOUND", message: "missing" });
  });

  test("maps generic error as INTERNAL_ERROR", () => {
    const error = asAppError(new Error("boom"));
    expect(error).toEqual({ code: "INTERNAL_ERROR", message: "boom" });
  });
});
