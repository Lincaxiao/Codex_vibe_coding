export type ErrorCode =
  | "VALIDATION_ERROR"
  | "NOT_FOUND"
  | "DB_ERROR"
  | "IO_ERROR"
  | "IMPORT_FORMAT_ERROR"
  | "CLIPBOARD_ERROR"
  | "INTERNAL_ERROR";

export type AppError = {
  code: ErrorCode;
  message: string;
};

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; error: AppError };

export type HealthPayload = {
  status: "ok";
  mode: "ready";
  appVersion: string;
  dbPath: string;
};

export type Prompt = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  isDeleted: boolean;
  createdAt: string;
  updatedAt: string;
};

export type PromptListInput = {
  query: string;
  includeDeleted: boolean;
  limit: number;
  offset: number;
};

export type PromptListOutput = {
  items: Prompt[];
  total: number;
};

export type PromptUpsertInput = {
  title: string;
  body: string;
  tags: string[];
};

export type PromptDeleteOutput = {
  deleted: true;
};

export type PromptRenderInput = {
  promptId: string;
  variables: Record<string, string>;
};

export type PromptRenderOutput = {
  content: string;
};

export type PromptCopyOutput = {
  copied: true;
  content: string;
};

export type ImportJsonInput = {
  inputPath: string;
};

export type ImportJsonOutput = {
  added: number;
  skipped: number;
};

export type ExportJsonInput = {
  outputPath: string;
  includeDeleted: boolean;
};

export type ExportMarkdownInput = {
  outputPath: string;
  includeDeleted: boolean;
};

export type ExportOutput = {
  outputPath: string;
};

export type VaultApi = {
  health: () => Promise<Result<HealthPayload>>;
  prompt: {
    list: (input: PromptListInput) => Promise<Result<PromptListOutput>>;
    get: (promptId: string) => Promise<Result<Prompt>>;
    create: (input: PromptUpsertInput) => Promise<Result<Prompt>>;
    update: (promptId: string, input: PromptUpsertInput) => Promise<Result<Prompt>>;
    softDelete: (promptId: string) => Promise<Result<PromptDeleteOutput>>;
    render: (input: PromptRenderInput) => Promise<Result<PromptRenderOutput>>;
    copyRendered: (input: PromptRenderInput) => Promise<Result<PromptCopyOutput>>;
    importJson: (input: ImportJsonInput) => Promise<Result<ImportJsonOutput>>;
    exportJson: (input: ExportJsonInput) => Promise<Result<ExportOutput>>;
    exportMarkdown: (input: ExportMarkdownInput) => Promise<Result<ExportOutput>>;
  };
};
