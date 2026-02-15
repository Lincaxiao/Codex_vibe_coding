import type { Result } from "../shared/types";
import { asAppError } from "./appError";

export function ok<T>(data: T): Result<T> {
  return { ok: true, data };
}

export function fail<T>(error: ReturnType<typeof asAppError>): Result<T> {
  return { ok: false, error };
}

export function toAppError(raw: unknown): ReturnType<typeof asAppError> {
  return asAppError(raw);
}
