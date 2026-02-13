import type {
  FileResult,
  MetaResponse,
  SessionItem,
  StatsResponse,
  TimerStartRequest,
  TimerState
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
      // keep plain text detail
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

export function getMeta(): Promise<MetaResponse> {
  return request<MetaResponse>("/api/v1/meta");
}

export function getTimerState(): Promise<TimerState> {
  return request<TimerState>("/api/v1/timer/state");
}

export function startTimer(payload: TimerStartRequest): Promise<TimerState> {
  return request<TimerState>("/api/v1/timer/start", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function stopTimer(): Promise<TimerState> {
  return request<TimerState>("/api/v1/timer/stop", {
    method: "POST"
  });
}

export function getStats(): Promise<StatsResponse> {
  return request<StatsResponse>("/api/v1/stats");
}

export function listSessions(params: {
  since?: string;
  tag?: string;
  taskContains?: string;
  limit: number;
}): Promise<SessionItem[]> {
  const query = new URLSearchParams();
  if (params.since?.trim()) {
    query.set("since", params.since.trim());
  }
  if (params.tag?.trim()) {
    query.set("tag", params.tag.trim());
  }
  if (params.taskContains?.trim()) {
    query.set("task_contains", params.taskContains.trim());
  }
  query.set("limit", String(params.limit));
  return request<SessionItem[]>(`/api/v1/sessions?${query.toString()}`);
}

export function exportCsv(outDir?: string): Promise<FileResult> {
  return request<FileResult>("/api/v1/export/csv", {
    method: "POST",
    body: JSON.stringify({ out_dir: outDir?.trim() || null })
  });
}

export function generateWeeklyReport(payload: {
  year?: number | null;
  week?: number | null;
  outDir?: string;
}): Promise<FileResult> {
  return request<FileResult>("/api/v1/report/weekly", {
    method: "POST",
    body: JSON.stringify({
      year: payload.year ?? null,
      week: payload.week ?? null,
      out_dir: payload.outDir?.trim() || null
    })
  });
}
