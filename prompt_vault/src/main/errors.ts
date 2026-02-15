import type { AppError, ErrorCode, Result } from "../shared/types";

function inferCode(message: string): ErrorCode {
  if (message.includes("不能为空")) {
    return "VALIDATION_ERROR";
  }
  if (message.includes("不存在")) {
    return "NOT_FOUND";
  }
  return "DB_ERROR";
}

export function ok<T>(data: T): Result<T> {
  return { ok: true, data };
}

export function fail<T>(error: AppError): Result<T> {
  return { ok: false, error };
}

export function toAppError(raw: unknown): AppError {
  if (raw instanceof Error) {
    return {
      code: inferCode(raw.message),
      message: raw.message,
    };
  }
  return {
    code: "INTERNAL_ERROR",
    message: "发生未知错误",
  };
}
