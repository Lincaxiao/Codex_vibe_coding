import { AppException } from "./appError";
import type { PromptListInput, PromptRenderInput, PromptUpsertInput } from "../shared/types";

const MAX_QUERY_LENGTH = 200;
const MAX_TITLE_LENGTH = 300;
const MAX_BODY_LENGTH = 100_000;
const MAX_TAGS = 64;
const MAX_TAG_LENGTH = 64;
const MAX_RENDER_VARIABLES = 100;
const MAX_RENDER_VARIABLE_KEY = 64;
const MAX_RENDER_VARIABLE_VALUE = 2000;

function assertObject(value: unknown, fieldName: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AppException("VALIDATION_ERROR", `${fieldName} 必须是对象`);
  }
  return value as Record<string, unknown>;
}

function assertString(value: unknown, fieldName: string, maxLength = 200): string {
  if (typeof value !== "string") {
    throw new AppException("VALIDATION_ERROR", `${fieldName} 必须是字符串`);
  }
  if (value.length > maxLength) {
    throw new AppException("VALIDATION_ERROR", `${fieldName} 超过最大长度 ${maxLength}`);
  }
  return value;
}

function assertPromptId(raw: unknown): string {
  const promptId = assertString(raw, "promptId", 128).trim();
  if (!promptId) {
    throw new AppException("VALIDATION_ERROR", "promptId 不能为空");
  }
  return promptId;
}

export function normalizePromptListInput(raw: unknown): PromptListInput {
  const input = assertObject(raw, "listInput");

  const queryRaw = input.query ?? "";
  const includeDeletedRaw = input.includeDeleted ?? false;
  const limitRaw = input.limit ?? 50;
  const offsetRaw = input.offset ?? 0;

  if (typeof includeDeletedRaw !== "boolean") {
    throw new AppException("VALIDATION_ERROR", "includeDeleted 必须是布尔值");
  }

  if (typeof limitRaw !== "number" || !Number.isFinite(limitRaw)) {
    throw new AppException("VALIDATION_ERROR", "limit 必须是数字");
  }
  if (typeof offsetRaw !== "number" || !Number.isFinite(offsetRaw)) {
    throw new AppException("VALIDATION_ERROR", "offset 必须是数字");
  }

  const query = assertString(queryRaw, "query", MAX_QUERY_LENGTH);

  return {
    query,
    includeDeleted: includeDeletedRaw,
    limit: Math.max(1, Math.min(Math.trunc(limitRaw), 200)),
    offset: Math.max(0, Math.trunc(offsetRaw)),
  };
}

export function normalizePromptUpsertInput(raw: unknown): PromptUpsertInput {
  const input = assertObject(raw, "promptUpsertInput");

  const title = assertString(input.title, "title", MAX_TITLE_LENGTH);
  const body = assertString(input.body, "body", MAX_BODY_LENGTH);

  if (!Array.isArray(input.tags)) {
    throw new AppException("VALIDATION_ERROR", "tags 必须是字符串数组");
  }

  if (input.tags.length > MAX_TAGS) {
    throw new AppException("VALIDATION_ERROR", `tags 数量不能超过 ${MAX_TAGS}`);
  }

  const tags = input.tags.map((value, index) =>
    assertString(value, `tags[${index}]`, MAX_TAG_LENGTH)
  );

  return {
    title,
    body,
    tags,
  };
}

export function normalizeUpdatePayload(raw: unknown): { promptId: string; input: PromptUpsertInput } {
  const payload = assertObject(raw, "updatePayload");

  return {
    promptId: assertPromptId(payload.promptId),
    input: normalizePromptUpsertInput(payload.input),
  };
}

export function normalizePromptRenderInput(raw: unknown): PromptRenderInput {
  const payload = assertObject(raw, "renderPayload");
  const promptId = assertPromptId(payload.promptId);

  const rawVariables = assertObject(payload.variables, "variables");
  const keys = Object.keys(rawVariables);
  if (keys.length > MAX_RENDER_VARIABLES) {
    throw new AppException("VALIDATION_ERROR", `variables 数量不能超过 ${MAX_RENDER_VARIABLES}`);
  }

  const variables: Record<string, string> = {};
  for (const key of keys) {
    if (key.length > MAX_RENDER_VARIABLE_KEY) {
      throw new AppException("VALIDATION_ERROR", `变量名超过最大长度 ${MAX_RENDER_VARIABLE_KEY}`);
    }
    const value = assertString(rawVariables[key], `variables.${key}`, MAX_RENDER_VARIABLE_VALUE);
    variables[key] = value;
  }

  return {
    promptId,
    variables,
  };
}

export function normalizeIncludeDeletedPayload(raw: unknown): { includeDeleted: boolean } {
  const payload = assertObject(raw, "includeDeletedPayload");
  if (typeof payload.includeDeleted !== "boolean") {
    throw new AppException("VALIDATION_ERROR", "includeDeleted 必须是布尔值");
  }
  return {
    includeDeleted: payload.includeDeleted,
  };
}

export function normalizePromptId(raw: unknown): string {
  return assertPromptId(raw);
}
