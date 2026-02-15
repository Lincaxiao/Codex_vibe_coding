import type { AppError, ErrorCode } from "../shared/types";

export class AppException extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode, message: string) {
    super(message);
    this.code = code;
    this.name = "AppException";
  }
}

export function asAppError(error: unknown): AppError {
  if (error instanceof AppException) {
    return {
      code: error.code,
      message: error.message,
    };
  }

  if (error instanceof Error) {
    return {
      code: "INTERNAL_ERROR",
      message: error.message || "发生未知错误",
    };
  }

  return {
    code: "INTERNAL_ERROR",
    message: "发生未知错误",
  };
}
