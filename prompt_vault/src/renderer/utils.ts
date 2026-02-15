export function parseTags(raw: string): string[] {
  return raw
    .split(/[，,\n]/g)
    .map((part) => part.trim())
    .filter((part, index, arr) => part.length > 0 && arr.indexOf(part) === index);
}

export function parseVariables(raw: string): Record<string, string> {
  const vars: Record<string, string> = {};
  const tokens = raw
    .split(/[;\n]/g)
    .map((line) => line.trim())
    .filter(Boolean);

  for (const token of tokens) {
    const idx = token.indexOf("=");
    if (idx <= 0) {
      throw new Error(`变量格式错误: ${token}`);
    }
    const key = token.slice(0, idx).trim();
    const value = token.slice(idx + 1);
    if (!key) {
      throw new Error(`变量名不能为空: ${token}`);
    }
    vars[key] = value;
  }

  return vars;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

export function formatSensitivePath(rawPath: string | null): string {
  if (!rawPath) {
    return "未设置";
  }

  const normalized = rawPath.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 0) {
    return rawPath;
  }
  if (parts.length === 1) {
    return parts[0];
  }

  return `.../${parts.slice(-2).join("/")}`;
}
