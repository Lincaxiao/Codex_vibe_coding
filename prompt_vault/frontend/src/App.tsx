import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  copyPrompt,
  createPrompt,
  deletePrompt,
  exportPrompts,
  getPrompt,
  importPrompts,
  listPrompts,
  renderPrompt,
  updatePrompt
} from "./api";
import { formatDate, parseTags, parseVariables } from "./utils";

type FormValues = {
  title: string;
  tags: string;
  body: string;
};

type ToastLevel = "success" | "error" | "info";

type ToastItem = {
  id: number;
  level: ToastLevel;
  text: string;
};

const EMPTY_FORM: FormValues = {
  title: "",
  tags: "",
  body: ""
};

const DEFAULT_EXPORT_JSON = "prompt_vault/exports/prompts.json";
const DEFAULT_EXPORT_MD = "prompt_vault/exports/prompts.md";

type ModalProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
};

function Modal({ open, title, onClose, children, footer }: ModalProps) {
  if (!open) {
    return null;
  }
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal-card" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <strong>{title}</strong>
          <button className="btn btn-ghost" onClick={onClose} type="button">
            关闭
          </button>
        </div>
        <div className="modal-body">{children}</div>
        <div className="modal-footer">{footer}</div>
      </div>
    </div>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [search, setSearch] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isCreatingNew, setIsCreatingNew] = useState(false);

  const [renderVars, setRenderVars] = useState("");
  const [renderedContent, setRenderedContent] = useState("");

  const [status, setStatus] = useState("就绪");
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [importPath, setImportPath] = useState("");
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<"json" | "markdown">("json");
  const [exportPath, setExportPath] = useState(DEFAULT_EXPORT_JSON);
  const [exportIncludeDeleted, setExportIncludeDeleted] = useState(false);

  const { register, reset, handleSubmit, formState } = useForm<FormValues>({
    defaultValues: EMPTY_FORM
  });

  const listQuery = useQuery({
    queryKey: ["prompts", search, includeDeleted],
    queryFn: () => listPrompts(search, includeDeleted)
  });

  const prompts = listQuery.data?.items ?? [];

  const detailQuery = useQuery({
    queryKey: ["prompt", selectedId],
    queryFn: () => getPrompt(selectedId as number),
    enabled: selectedId !== null && !isCreatingNew
  });

  const addToast = useCallback((level: ToastLevel, text: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((prev) => [...prev, { id, level, text }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 2600);
  }, []);

  const refreshPromptList = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["prompts"] });
  }, [queryClient]);

  useEffect(() => {
    if (!prompts.length) {
      setSelectedId(null);
      if (!isCreatingNew) {
        reset(EMPTY_FORM);
      }
      return;
    }
    if (isCreatingNew) {
      return;
    }
    if (selectedId === null) {
      setSelectedId(prompts[0].id);
      return;
    }
    const exists = prompts.some((item) => item.id === selectedId);
    if (!exists) {
      setSelectedId(prompts[0].id);
    }
  }, [prompts, selectedId, isCreatingNew, reset]);

  useEffect(() => {
    const detail = detailQuery.data;
    if (!detail || isCreatingNew) {
      return;
    }
    reset({
      title: detail.title,
      tags: detail.tags.join(", "),
      body: detail.body
    });
    setStatus(`已加载 ID=${detail.id}`);
  }, [detailQuery.data, isCreatingNew, reset]);

  const createMutation = useMutation({
    mutationFn: createPrompt,
    onSuccess: async (prompt) => {
      setIsCreatingNew(false);
      setSelectedId(prompt.id);
      await refreshPromptList();
      await queryClient.invalidateQueries({ queryKey: ["prompt", prompt.id] });
      setStatus(`已新增提示词 ID=${prompt.id}`);
      addToast("success", "提示词已新增");
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { title: string; body: string; tags: string[] } }) =>
      updatePrompt(id, payload),
    onSuccess: async (prompt) => {
      await refreshPromptList();
      await queryClient.invalidateQueries({ queryKey: ["prompt", prompt.id] });
      setStatus(`已更新提示词 ID=${prompt.id}`);
      addToast("success", "提示词已更新");
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deletePrompt,
    onSuccess: async () => {
      const deleted = selectedId;
      setDeleteModalOpen(false);
      setSelectedId(null);
      setRenderedContent("");
      setIsCreatingNew(false);
      await refreshPromptList();
      setStatus(`已软删除 ID=${deleted ?? "-"}`);
      addToast("success", "提示词已软删除");
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const renderMutation = useMutation({
    mutationFn: ({ id, variables }: { id: number; variables: Record<string, string> }) => renderPrompt(id, variables),
    onSuccess: (result) => {
      setRenderedContent(result.content);
      setStatus("渲染完成");
      addToast("success", "渲染完成");
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const copyMutation = useMutation({
    mutationFn: ({ id, variables }: { id: number; variables: Record<string, string> }) => copyPrompt(id, variables),
    onSuccess: (result) => {
      setRenderedContent(result.content);
      setStatus(result.message);
      addToast(result.copied ? "success" : "error", result.message);
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const importMutation = useMutation({
    mutationFn: importPrompts,
    onSuccess: async (result) => {
      setImportModalOpen(false);
      await refreshPromptList();
      const message = `导入完成：新增 ${result.added}，跳过 ${result.skipped}`;
      setStatus(message);
      addToast("success", message);
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const exportMutation = useMutation({
    mutationFn: exportPrompts,
    onSuccess: (result) => {
      setExportModalOpen(false);
      const message = `导出完成：${result.output_path}`;
      setStatus(message);
      addToast("success", message);
    },
    onError: (error: Error) => {
      setStatus(error.message);
      addToast("error", error.message);
    }
  });

  const busy =
    formState.isSubmitting ||
    createMutation.isPending ||
    updateMutation.isPending ||
    deleteMutation.isPending ||
    importMutation.isPending ||
    exportMutation.isPending;

  const currentPromptMeta = useMemo(() => {
    if (selectedId === null) {
      return null;
    }
    return prompts.find((item) => item.id === selectedId) ?? null;
  }, [prompts, selectedId]);

  const runSubmit = useCallback(
    async (values: FormValues) => {
      const payload = {
        title: values.title.trim(),
        body: values.body,
        tags: parseTags(values.tags)
      };
      if (!payload.title) {
        addToast("error", "标题不能为空");
        return;
      }
      if (!payload.body.trim()) {
        addToast("error", "正文不能为空");
        return;
      }

      if (isCreatingNew || selectedId === null) {
        await createMutation.mutateAsync(payload);
        return;
      }
      await updateMutation.mutateAsync({ id: selectedId, payload });
    },
    [addToast, createMutation, isCreatingNew, selectedId, updateMutation]
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const isMeta = event.ctrlKey || event.metaKey;
      if (!isMeta) {
        return;
      }
      const key = event.key.toLowerCase();
      if (key === "s") {
        event.preventDefault();
        void handleSubmit(runSubmit)();
      }
      if (key === "f") {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
      if (key === "n") {
        event.preventDefault();
        setIsCreatingNew(true);
        setSelectedId(null);
        setRenderedContent("");
        reset(EMPTY_FORM);
        setStatus("已切换到新建模式");
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleSubmit, reset, runSubmit]);

  useEffect(() => {
    const hasModal = deleteModalOpen || importModalOpen || exportModalOpen;
    document.body.style.overflow = hasModal ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [deleteModalOpen, importModalOpen, exportModalOpen]);

  const selectPrompt = (id: number) => {
    setIsCreatingNew(false);
    setSelectedId(id);
    setRenderedContent("");
  };

  const createNewPrompt = () => {
    setIsCreatingNew(true);
    setSelectedId(null);
    setRenderedContent("");
    reset(EMPTY_FORM);
    setStatus("已切换到新建模式");
  };

  const openDeleteModal = () => {
    if (selectedId === null || isCreatingNew) {
      addToast("error", "请先选择一个提示词");
      return;
    }
    setDeleteModalOpen(true);
  };

  const handleRender = () => {
    if (selectedId === null || isCreatingNew) {
      addToast("error", "请先选择一个提示词");
      return;
    }
    let variables: Record<string, string> = {};
    try {
      variables = parseVariables(renderVars);
    } catch (error) {
      const message = error instanceof Error ? error.message : "变量格式错误";
      setStatus(message);
      addToast("error", message);
      return;
    }
    renderMutation.mutate({ id: selectedId, variables });
  };

  const handleCopyRendered = () => {
    if (selectedId === null || isCreatingNew) {
      addToast("error", "请先选择一个提示词");
      return;
    }
    let variables: Record<string, string> = {};
    try {
      variables = parseVariables(renderVars);
    } catch (error) {
      const message = error instanceof Error ? error.message : "变量格式错误";
      setStatus(message);
      addToast("error", message);
      return;
    }
    copyMutation.mutate({ id: selectedId, variables });
  };

  const openImportModal = () => {
    setImportPath("");
    setImportModalOpen(true);
  };

  const confirmImport = () => {
    const value = importPath.trim();
    if (!value) {
      addToast("error", "导入路径不能为空");
      return;
    }
    importMutation.mutate(value);
  };

  const openExportModal = () => {
    setExportFormat("json");
    setExportPath(DEFAULT_EXPORT_JSON);
    setExportIncludeDeleted(false);
    setExportModalOpen(true);
  };

  const onExportFormatChange = (next: "json" | "markdown") => {
    setExportFormat(next);
    setExportPath(next === "json" ? DEFAULT_EXPORT_JSON : DEFAULT_EXPORT_MD);
  };

  const confirmExport = () => {
    const outputPath = exportPath.trim();
    if (!outputPath) {
      addToast("error", "导出路径不能为空");
      return;
    }
    exportMutation.mutate({
      format: exportFormat,
      outputPath,
      includeDeleted: exportIncludeDeleted
    });
  };

  return (
    <div className="app-shell">
      <header className="px-5 py-4">
        <div className="panel flex items-center justify-between px-4 py-3">
          <div>
            <h1 className="m-0 text-[20px] font-semibold">Prompt Vault</h1>
            <p className="m-0 text-sm muted">本地优先提示词管理器（WebView 版）</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn btn-ghost" onClick={() => void listQuery.refetch()} type="button">
              刷新
            </button>
            <button className="btn btn-ghost" onClick={openImportModal} type="button">
              导入
            </button>
            <button className="btn btn-ghost" onClick={openExportModal} type="button">
              导出
            </button>
            <button className="btn btn-primary" onClick={createNewPrompt} type="button">
              新建
            </button>
          </div>
        </div>
      </header>

      <main className="app-main px-5 pb-4">
        <div className="workspace-grid">
          <section className="panel flex min-h-0 flex-col p-4">
            <div className="mb-3 flex gap-2">
              <input
                ref={searchInputRef}
                className="field"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索标题/正文/标签"
              />
            </div>
            <label className="mb-3 flex items-center gap-2 text-sm muted">
              <input
                type="checkbox"
                checked={includeDeleted}
                onChange={(event) => setIncludeDeleted(event.target.checked)}
              />
              包含已删除
            </label>
            <div className="mb-2 text-sm muted">总数：{listQuery.data?.total ?? 0}</div>
            <div className="min-h-0 flex-1 overflow-auto rounded-[10px] border border-[#d6deea] bg-white">
              {prompts.length === 0 ? (
                <div className="p-4 text-sm muted">暂无匹配提示词</div>
              ) : (
                <ul className="m-0 list-none p-0">
                  {prompts.map((prompt) => (
                    <li key={prompt.id}>
                      <button
                        className={`w-full border-b border-[#eef2f7] px-3 py-3 text-left transition-colors ${
                          selectedId === prompt.id && !isCreatingNew
                            ? "bg-[#ebf3ff]"
                            : "bg-white hover:bg-[#f8fbff]"
                        }`}
                        onClick={() => selectPrompt(prompt.id)}
                        type="button"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <strong className="truncate text-[14px]">{prompt.title}</strong>
                          <span
                            className={`rounded-full px-2 py-[2px] text-[11px] ${
                              prompt.is_deleted ? "bg-[#fef2f2] text-[#b91c1c]" : "bg-[#edf7f1] text-[#166534]"
                            }`}
                          >
                            {prompt.is_deleted ? "deleted" : "active"}
                          </span>
                        </div>
                        <div className="mt-1 text-[12px] muted">{formatDate(prompt.updated_at)}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="panel min-h-0 flex flex-col p-4">
            <form className="flex h-full min-h-0 flex-col gap-3" onSubmit={handleSubmit(runSubmit)}>
              <div className="flex items-center justify-between">
                <strong className="text-[15px]">编辑区</strong>
                <span className="text-xs muted">
                  {isCreatingNew ? "新建" : currentPromptMeta ? `ID=${currentPromptMeta.id}` : "未选择"}
                </span>
              </div>

              <label className="text-sm">
                <div className="mb-1 font-medium">标题</div>
                <input className="field" {...register("title")} />
              </label>

              <label className="text-sm">
                <div className="mb-1 font-medium">标签（逗号分隔）</div>
                <input className="field" {...register("tags")} />
              </label>

              <label className="text-sm min-h-0 flex-1">
                <div className="mb-1 font-medium">正文</div>
                <textarea className="field h-full min-h-[240px] resize-y" {...register("body")} />
              </label>

              <div className="grid grid-cols-2 gap-2 rounded-[10px] border border-[#dce5f0] bg-[#f8fbff] px-3 py-2 text-[12px] muted">
                <span>创建时间：{detailQuery.data ? formatDate(detailQuery.data.created_at) : "-"}</span>
                <span>更新时间：{detailQuery.data ? formatDate(detailQuery.data.updated_at) : "-"}</span>
              </div>

              <div className="flex flex-wrap gap-2">
                <button className="btn btn-primary" type="submit" disabled={busy}>
                  {isCreatingNew ? "创建" : "保存"}
                </button>
                <button className="btn btn-danger" type="button" onClick={openDeleteModal} disabled={busy}>
                  软删除
                </button>
              </div>
            </form>
          </section>

          <section className="panel min-h-0 p-4">
            <div className="mb-2 flex items-center justify-between">
              <strong className="text-[15px]">渲染区</strong>
              <span className="text-xs muted">key=value;key2=value2</span>
            </div>
            <label className="text-sm">
              <div className="mb-1 font-medium">变量输入</div>
              <textarea
                className="field min-h-[120px] resize-y"
                value={renderVars}
                onChange={(event) => setRenderVars(event.target.value)}
                placeholder="name=张三;date=2026-02-13"
              />
            </label>
            <div className="mt-3 flex gap-2">
              <button className="btn btn-ghost" type="button" onClick={handleRender} disabled={renderMutation.isPending}>
                渲染
              </button>
              <button
                className="btn btn-primary"
                type="button"
                onClick={handleCopyRendered}
                disabled={copyMutation.isPending}
              >
                复制渲染结果
              </button>
            </div>
            <label className="mt-3 block min-h-0 flex-1 text-sm">
              <div className="mb-1 font-medium">渲染预览</div>
              <textarea
                className="field h-full min-h-[220px] resize-y"
                value={renderedContent}
                onChange={(event) => setRenderedContent(event.target.value)}
              />
            </label>
          </section>
        </div>
      </main>

      <footer className="px-5 pb-4">
        <div className="panel flex items-center justify-between px-4 py-2 text-sm">
          <span className="muted">{status}</span>
          <span className="muted">Ctrl/Cmd+S 保存 · Ctrl/Cmd+F 搜索 · Ctrl/Cmd+N 新建</span>
        </div>
      </footer>

      <div className="pointer-events-none fixed right-4 top-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-[10px] px-3 py-2 text-sm text-white shadow-lg ${
              toast.level === "success" ? "bg-[#0f9d58]" : toast.level === "error" ? "bg-[#dc2626]" : "bg-[#1f3f84]"
            }`}
          >
            {toast.text}
          </div>
        ))}
      </div>

      <Modal
        open={deleteModalOpen}
        title="确认软删除"
        onClose={() => setDeleteModalOpen(false)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setDeleteModalOpen(false)} type="button">
              取消
            </button>
            <button
              className="btn btn-danger"
              onClick={() => {
                if (selectedId !== null) {
                  deleteMutation.mutate(selectedId);
                }
              }}
              type="button"
              disabled={deleteMutation.isPending}
            >
              确认删除
            </button>
          </>
        }
      >
        <p className="m-0 text-sm muted">该操作为软删除（仅标记删除，不会清理数据库原始记录）。</p>
      </Modal>

      <Modal
        open={importModalOpen}
        title="导入 JSON"
        onClose={() => setImportModalOpen(false)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setImportModalOpen(false)} type="button">
              取消
            </button>
            <button className="btn btn-primary" onClick={confirmImport} type="button" disabled={importMutation.isPending}>
              开始导入
            </button>
          </>
        }
      >
        <label className="text-sm">
          <div className="mb-1 font-medium">JSON 文件路径</div>
          <input
            className="field"
            value={importPath}
            onChange={(event) => setImportPath(event.target.value)}
            placeholder="prompt_vault/exports/prompts.json"
          />
        </label>
      </Modal>

      <Modal
        open={exportModalOpen}
        title="导出提示词"
        onClose={() => setExportModalOpen(false)}
        footer={
          <>
            <button className="btn btn-ghost" onClick={() => setExportModalOpen(false)} type="button">
              取消
            </button>
            <button className="btn btn-primary" onClick={confirmExport} type="button" disabled={exportMutation.isPending}>
              开始导出
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <label className="text-sm block">
            <div className="mb-1 font-medium">导出格式</div>
            <select className="field" value={exportFormat} onChange={(e) => onExportFormatChange(e.target.value as "json" | "markdown")}>
              <option value="json">json</option>
              <option value="markdown">markdown</option>
            </select>
          </label>
          <label className="text-sm block">
            <div className="mb-1 font-medium">导出路径</div>
            <input className="field" value={exportPath} onChange={(event) => setExportPath(event.target.value)} />
          </label>
          <label className="flex items-center gap-2 text-sm muted">
            <input
              type="checkbox"
              checked={exportIncludeDeleted}
              onChange={(event) => setExportIncludeDeleted(event.target.checked)}
            />
            包含已删除记录
          </label>
        </div>
      </Modal>
    </div>
  );
}

