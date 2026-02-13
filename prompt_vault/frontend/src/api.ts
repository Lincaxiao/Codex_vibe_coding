import type {
  PromptCopyResponse,
  PromptDetail,
  PromptExportResponse,
  PromptImportResponse,
  PromptListResponse,
  PromptRenderResponse
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json"
    },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text || `HTTP ${response.status}`;
    try {
      const parsed = JSON.parse(text) as { detail?: string };
      if (parsed.detail) {
        detail = parsed.detail;
      }
    } catch {
      // Keep plain text detail.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function listPrompts(query: string, includeDeleted: boolean): Promise<PromptListResponse> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("query", query.trim());
  }
  if (includeDeleted) {
    params.set("include_deleted", "true");
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<PromptListResponse>(`/api/prompts${suffix}`);
}

export function getPrompt(id: number): Promise<PromptDetail> {
  return request<PromptDetail>(`/api/prompts/${id}`);
}

export function createPrompt(payload: { title: string; body: string; tags: string[] }): Promise<PromptDetail> {
  return request<PromptDetail>("/api/prompts", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updatePrompt(
  id: number,
  payload: { title: string; body: string; tags: string[] }
): Promise<PromptDetail> {
  return request<PromptDetail>(`/api/prompts/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deletePrompt(id: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/prompts/${id}`, {
    method: "DELETE"
  });
}

export function renderPrompt(id: number, variables: Record<string, string>): Promise<PromptRenderResponse> {
  return request<PromptRenderResponse>(`/api/prompts/${id}/render`, {
    method: "POST",
    body: JSON.stringify({ variables })
  });
}

export function copyPrompt(id: number, variables: Record<string, string>): Promise<PromptCopyResponse> {
  return request<PromptCopyResponse>(`/api/prompts/${id}/copy`, {
    method: "POST",
    body: JSON.stringify({ variables })
  });
}

export function importPrompts(inputPath: string): Promise<PromptImportResponse> {
  return request<PromptImportResponse>("/api/import", {
    method: "POST",
    body: JSON.stringify({ input_path: inputPath })
  });
}

export function exportPrompts(payload: {
  format: "json" | "markdown";
  outputPath: string;
  includeDeleted: boolean;
}): Promise<PromptExportResponse> {
  return request<PromptExportResponse>("/api/export", {
    method: "POST",
    body: JSON.stringify({
      format: payload.format,
      output_path: payload.outputPath,
      include_deleted: payload.includeDeleted
    })
  });
}
