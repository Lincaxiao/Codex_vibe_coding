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
  dbPath: string | null;
  storageConfigured: boolean;
  storageFolder: string | null;
};

export type StorageConfig = {
  isConfigured: boolean;
  selectedFolder: string | null;
  dbPath: string | null;
  source: "env" | "user_selected" | "unset" | "corrupted";
  warning: string | null;
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

export type ImportFailure = {
  index: number;
  reason: string;
};

export type ImportJsonOutput = {
  added: number;
  skipped: number;
  sourcePath: string;
  failures: ImportFailure[];
};

export type ExportJsonInput = {
  includeDeleted: boolean;
};

export type ExportMarkdownInput = {
  includeDeleted: boolean;
};

export type ExportOutput = {
  outputPath: string;
};

export type MenuCommand = "new" | "save" | "focus-search";

export type VaultApi = {
  health: () => Promise<Result<HealthPayload>>;
  storage: {
    getConfig: () => Promise<Result<StorageConfig>>;
    chooseFolder: () => Promise<Result<StorageConfig>>;
  };
  prompt: {
    list: (input: PromptListInput) => Promise<Result<PromptListOutput>>;
    get: (promptId: string) => Promise<Result<Prompt>>;
    create: (input: PromptUpsertInput) => Promise<Result<Prompt>>;
    update: (promptId: string, input: PromptUpsertInput) => Promise<Result<Prompt>>;
    softDelete: (promptId: string) => Promise<Result<PromptDeleteOutput>>;
    render: (input: PromptRenderInput) => Promise<Result<PromptRenderOutput>>;
    copyRendered: (input: PromptRenderInput) => Promise<Result<PromptCopyOutput>>;
    importJson: () => Promise<Result<ImportJsonOutput>>;
    exportJson: (input: ExportJsonInput) => Promise<Result<ExportOutput>>;
    exportMarkdown: (input: ExportMarkdownInput) => Promise<Result<ExportOutput>>;
  };
  events: {
    onMenuCommand: (listener: (command: MenuCommand) => void) => () => void;
  };
};
