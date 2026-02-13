export interface PromptSummary {
  id: number;
  title: string;
  updated_at: string;
  is_deleted: boolean;
  tags: string[];
}

export interface PromptDetail {
  id: number;
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
  is_deleted: boolean;
  tags: string[];
}

export interface PromptListResponse {
  items: PromptSummary[];
  total: number;
}

export interface PromptRenderResponse {
  content: string;
}

export interface PromptCopyResponse {
  copied: boolean;
  content: string;
  message: string;
}

export interface PromptImportResponse {
  added: number;
  skipped: number;
}

export interface PromptExportResponse {
  output_path: string;
  format: "json" | "markdown";
}

