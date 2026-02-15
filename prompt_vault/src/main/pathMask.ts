import path from "node:path";

export function toPathLabel(absolutePath: string): string {
  return path.basename(absolutePath);
}
