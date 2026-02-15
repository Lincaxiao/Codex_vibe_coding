import type { AppError, ErrorCode, Result } from "../shared/types";

function inferCode(message: string): ErrorCode {
  if (message.startsWith("IMPORT_FORMAT_ERROR:")) {
    return "IMPORT_FORMAT_ERROR";
  }
  if (message.includes("不能为空")) {
    return "VALIDATION_ERROR";
  }
  if (message.includes("不存在")) {
    return "NOT_FOUND";
  }
  if (message.includes("剪贴板")) {
    return "CLIPBOARD_ERROR";
  }
  if (message.includes("IO") || message.includes("文件")) {
    return "IO_ERROR";
  }
  return "DB_ERROR";
}

function normalizeMessage(message: string): string {
  if (message.startsWith("IMPORT_FORMAT_ERROR:")) {
    return message.replace("IMPORT_FORMAT_ERROR:", "").trim();
  }
  return message;
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
      message: normalizeMessage(raw.message),
    };
  }
  return {
    code: "INTERNAL_ERROR",
    message: "发生未知错误",
  };
}
