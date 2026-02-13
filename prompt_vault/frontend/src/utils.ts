export function parseTags(raw: string): string[] {
  const parts = raw
    .split(/[,，\n]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
  return Array.from(new Set(parts));
}

export function parseVariables(raw: string): Record<string, string> {
  const result: Record<string, string> = {};
  const lines = raw
    .split(/[;\n]/)
    .map((line) => line.trim())
    .filter(Boolean);
  for (const line of lines) {
    const index = line.indexOf("=");
    if (index <= 0) {
      throw new Error(`变量格式错误: ${line}，请使用 key=value`);
    }
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1);
    if (!key) {
      throw new Error(`变量键不能为空: ${line}`);
    }
    result[key] = value;
  }
  return result;
}

export function formatDate(input: string): string {
  const date = new Date(input);
  if (Number.isNaN(date.getTime())) {
    return input;
  }
  return date.toLocaleString("zh-CN");
}
