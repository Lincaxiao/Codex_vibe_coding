export function formatCountdown(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const sec = safe % 60;
  const hours = Math.floor(mins / 60);
  const minOnly = mins % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minOnly).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  return `${String(minOnly).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(safe / 60);
  const sec = safe % 60;
  const hours = Math.floor(mins / 60);
  const minOnly = mins % 60;
  if (hours > 0) {
    return `${hours}小时${String(minOnly).padStart(2, "0")}分${String(sec).padStart(2, "0")}秒`;
  }
  return `${minOnly}分${String(sec).padStart(2, "0")}秒`;
}

export function formatDateTime(input: string): string {
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) {
    return input;
  }
  return date.toLocaleString("zh-CN");
}

export function parseNumberOrNull(raw: string): number | null {
  const text = raw.trim();
  if (!text) {
    return null;
  }
  const value = Number(text);
  if (Number.isNaN(value)) {
    return null;
  }
  return value;
}
