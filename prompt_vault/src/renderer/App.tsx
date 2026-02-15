import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { MenuCommand, Prompt } from "../shared/types";
import { formatDate, parseTags, parseVariables } from "./utils";

type FormState = {
  title: string;
  tags: string;
  body: string;
};

const EMPTY_FORM: FormState = {
  title: "",
  tags: "",
  body: "",
};

function Modal(props: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
}) {
  if (!props.open) {
    return null;
  }

  return (
    <div className="modal-backdrop" onClick={props.onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <strong>{props.title}</strong>
          <button className="btn ghost" onClick={props.onClose}>
            关闭
          </button>
        </div>
        <div className="modal-body">{props.children}</div>
        <div className="modal-foot">{props.footer}</div>
      </div>
    </div>
  );
}

export default function App() {
  const searchRef = useRef<HTMLInputElement>(null);

  const [status, setStatus] = useState("就绪");
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [items, setItems] = useState<Prompt[]>([]);
  const [total, setTotal] = useState(0);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const [renderVars, setRenderVars] = useState("");
  const [renderOutput, setRenderOutput] = useState("");
  const [busy, setBusy] = useState(false);

  const [importModalOpen, setImportModalOpen] = useState(false);

  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportFormat, setExportFormat] = useState<"json" | "markdown">("json");
  const [exportIncludeDeleted, setExportIncludeDeleted] = useState(false);

  const selectedMeta = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId]
  );

  const notify = useCallback((message: string) => {
    setStatus(message);
    setToast(message);
    window.setTimeout(() => setToast(""), 2200);
  }, []);

  const loadList = useCallback(async () => {
    setBusy(true);
    const result = await window.vault.prompt.list({
      query,
      includeDeleted,
      limit: 200,
      offset: 0,
    });
    setBusy(false);

    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    setItems(result.data.items);
    setTotal(result.data.total);

    if (result.data.items.length === 0) {
      setSelectedId(null);
      if (!isCreating) {
        setForm(EMPTY_FORM);
      }
      return;
    }

    if (isCreating) {
      return;
    }

    const exists = selectedId ? result.data.items.some((item) => item.id === selectedId) : false;
    if (!exists) {
      setSelectedId(result.data.items[0].id);
    }
  }, [includeDeleted, isCreating, notify, query, selectedId]);

  const loadDetail = useCallback(
    async (promptId: string) => {
      setBusy(true);
      const result = await window.vault.prompt.get(promptId);
      setBusy(false);

      if (!result.ok) {
        notify(result.error.message);
        return;
      }

      setForm({
        title: result.data.title,
        tags: result.data.tags.join(", "),
        body: result.data.body,
      });
      setStatus(`已加载 ${result.data.id}`);
    },
    [notify]
  );

  const createNew = useCallback(() => {
    setIsCreating(true);
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setRenderOutput("");
    setStatus("已切换到新建模式");
  }, []);

  const onSubmit = useCallback(async () => {
    const payload = {
      title: form.title.trim(),
      body: form.body,
      tags: parseTags(form.tags),
    };

    if (!payload.title) {
      notify("标题不能为空");
      return;
    }
    if (!payload.body.trim()) {
      notify("正文不能为空");
      return;
    }

    setBusy(true);
    if (isCreating || !selectedId) {
      const result = await window.vault.prompt.create(payload);
      setBusy(false);
      if (!result.ok) {
        notify(result.error.message);
        return;
      }
      notify(`已创建 ${result.data.id}`);
      setIsCreating(false);
      setSelectedId(result.data.id);
      await loadList();
      return;
    }

    const result = await window.vault.prompt.update(selectedId, payload);
    setBusy(false);
    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    notify(`已保存 ${result.data.id}`);
    await loadList();
  }, [form.body, form.tags, form.title, isCreating, loadList, notify, selectedId]);

  const onDelete = useCallback(async () => {
    if (!selectedId || isCreating) {
      notify("请先选择一条记录");
      return;
    }
    setBusy(true);
    const result = await window.vault.prompt.softDelete(selectedId);
    setBusy(false);
    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    notify("已软删除");
    setSelectedId(null);
    setRenderOutput("");
    await loadList();
  }, [isCreating, loadList, notify, selectedId]);

  const onRender = useCallback(async () => {
    if (!selectedId || isCreating) {
      notify("请先选择一条记录");
      return;
    }

    let variables: Record<string, string>;
    try {
      variables = parseVariables(renderVars);
    } catch (error) {
      notify(error instanceof Error ? error.message : "变量解析失败");
      return;
    }

    setBusy(true);
    const result = await window.vault.prompt.render({
      promptId: selectedId,
      variables,
    });
    setBusy(false);

    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    setRenderOutput(result.data.content);
    notify("渲染完成");
  }, [isCreating, notify, renderVars, selectedId]);

  const onCopy = useCallback(async () => {
    if (!selectedId || isCreating) {
      notify("请先选择一条记录");
      return;
    }

    let variables: Record<string, string>;
    try {
      variables = parseVariables(renderVars);
    } catch (error) {
      notify(error instanceof Error ? error.message : "变量解析失败");
      return;
    }

    setBusy(true);
    const result = await window.vault.prompt.copyRendered({
      promptId: selectedId,
      variables,
    });
    setBusy(false);

    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    setRenderOutput(result.data.content);
    notify("已复制渲染结果");
  }, [isCreating, notify, renderVars, selectedId]);

  const onConfirmImport = useCallback(async () => {
    setBusy(true);
    const result = await window.vault.prompt.importJson();
    setBusy(false);
    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    setImportModalOpen(false);
    notify(
      `导入完成：新增 ${result.data.added}，跳过 ${result.data.skipped}（${result.data.sourcePath}）`
    );
    await loadList();
  }, [loadList, notify]);

  const onConfirmExport = useCallback(async () => {
    setBusy(true);
    const result =
      exportFormat === "json"
        ? await window.vault.prompt.exportJson({ includeDeleted: exportIncludeDeleted })
        : await window.vault.prompt.exportMarkdown({
            includeDeleted: exportIncludeDeleted,
          });
    setBusy(false);

    if (!result.ok) {
      notify(result.error.message);
      return;
    }

    setExportModalOpen(false);
    notify(`导出完成：${result.data.outputPath}`);
  }, [exportFormat, exportIncludeDeleted, notify]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (!selectedId || isCreating) {
      return;
    }
    void loadDetail(selectedId);
  }, [isCreating, loadDetail, selectedId]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const withMeta = event.metaKey || event.ctrlKey;
      if (!withMeta) {
        return;
      }

      const key = event.key.toLowerCase();
      if (key === "f") {
        event.preventDefault();
        searchRef.current?.focus();
      } else if (key === "n") {
        event.preventDefault();
        createNew();
      } else if (key === "s") {
        event.preventDefault();
        void onSubmit();
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [createNew, onSubmit]);

  useEffect(() => {
    const off = window.vault.events.onMenuCommand((command: MenuCommand) => {
      if (command === "new") {
        createNew();
      } else if (command === "save") {
        void onSubmit();
      } else if (command === "focus-search") {
        searchRef.current?.focus();
      }
    });
    return off;
  }, [createNew, onSubmit]);

  return (
    <div className="shell">
      <header className="header card">
        <div>
          <h1>Prompt Vault</h1>
          <p>macOS local prompt workbench</p>
        </div>
        <div className="header-actions">
          <button className="btn ghost" onClick={() => void loadList()} disabled={busy}>
            刷新
          </button>
          <button className="btn ghost" onClick={() => setImportModalOpen(true)} disabled={busy}>
            导入
          </button>
          <button className="btn ghost" onClick={() => setExportModalOpen(true)} disabled={busy}>
            导出
          </button>
          <button className="btn ghost" onClick={createNew} disabled={busy}>
            新建
          </button>
        </div>
      </header>

      <main className="workspace">
        <section className="card list-col">
          <div className="toolbar-row">
            <input
              ref={searchRef}
              className="input"
              value={query}
              placeholder="搜索标题/正文/标签"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => setIncludeDeleted(e.target.checked)}
            />
            包含已删除
          </label>
          <div className="meta-text">总数: {total}</div>
          <div className="list-body">
            {items.length === 0 ? (
              <div className="empty">暂无数据</div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  className={`list-item ${selectedId === item.id && !isCreating ? "active" : ""}`}
                  onClick={() => {
                    setIsCreating(false);
                    setSelectedId(item.id);
                    setRenderOutput("");
                  }}
                >
                  <div className="list-title-row">
                    <strong>{item.title}</strong>
                    <span className={`badge ${item.isDeleted ? "deleted" : "ok"}`}>
                      {item.isDeleted ? "deleted" : "active"}
                    </span>
                  </div>
                  <div className="meta-text">{formatDate(item.updatedAt)}</div>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="card edit-col">
          <div className="section-title-row">
            <strong>编辑区</strong>
            <span className="meta-text">
              {isCreating ? "新建" : selectedMeta ? selectedMeta.id : "未选择"}
            </span>
          </div>

          <label className="field">
            <span>标题</span>
            <input
              className="input"
              value={form.title}
              onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
            />
          </label>

          <label className="field">
            <span>标签（逗号分隔）</span>
            <input
              className="input"
              value={form.tags}
              onChange={(e) => setForm((prev) => ({ ...prev, tags: e.target.value }))}
            />
          </label>

          <label className="field body-field">
            <span>正文</span>
            <textarea
              className="input textarea"
              value={form.body}
              onChange={(e) => setForm((prev) => ({ ...prev, body: e.target.value }))}
            />
          </label>

          <div className="meta-grid">
            <span>创建时间: {selectedMeta ? formatDate(selectedMeta.createdAt) : "-"}</span>
            <span>更新时间: {selectedMeta ? formatDate(selectedMeta.updatedAt) : "-"}</span>
          </div>

          <div className="actions">
            <button className="btn primary" onClick={() => void onSubmit()} disabled={busy}>
              {isCreating ? "创建" : "保存"}
            </button>
            <button className="btn danger" onClick={() => void onDelete()} disabled={busy}>
              软删除
            </button>
          </div>
        </section>

        <section className="card render-col">
          <div className="section-title-row">
            <strong>渲染区</strong>
            <span className="meta-text">key=value;key2=value2</span>
          </div>

          <label className="field">
            <span>变量输入</span>
            <textarea
              className="input small-textarea"
              value={renderVars}
              onChange={(e) => setRenderVars(e.target.value)}
              placeholder="name=Alice;date=2026-02-15"
            />
          </label>

          <div className="actions">
            <button className="btn ghost" onClick={() => void onRender()} disabled={busy}>
              渲染
            </button>
            <button className="btn primary" onClick={() => void onCopy()} disabled={busy}>
              复制渲染结果
            </button>
          </div>

          <label className="field body-field">
            <span>渲染预览</span>
            <textarea
              className="input textarea"
              value={renderOutput}
              onChange={(e) => setRenderOutput(e.target.value)}
            />
          </label>
        </section>
      </main>

      <footer className="footer card">
        <span>{status}</span>
        <span>Cmd+N 新建 · Cmd+S 保存 · Cmd+F 搜索</span>
      </footer>

      {toast ? <div className="toast">{toast}</div> : null}

      <Modal
        open={importModalOpen}
        title="导入 JSON"
        onClose={() => setImportModalOpen(false)}
        footer={
          <>
            <button className="btn ghost" onClick={() => setImportModalOpen(false)}>
              取消
            </button>
            <button className="btn primary" onClick={() => void onConfirmImport()} disabled={busy}>
              开始导入
            </button>
          </>
        }
      >
        <label className="field">
          <span>将从系统文件选择器选择 JSON 文件。</span>
        </label>
      </Modal>

      <Modal
        open={exportModalOpen}
        title="导出提示词"
        onClose={() => setExportModalOpen(false)}
        footer={
          <>
            <button className="btn ghost" onClick={() => setExportModalOpen(false)}>
              取消
            </button>
            <button className="btn primary" onClick={() => void onConfirmExport()} disabled={busy}>
              开始导出
            </button>
          </>
        }
      >
        <label className="field">
          <span>导出格式</span>
          <select
            className="input"
            value={exportFormat}
            onChange={(e) => {
              const format = e.target.value as "json" | "markdown";
              setExportFormat(format);
            }}
          >
            <option value="json">json</option>
            <option value="markdown">markdown</option>
          </select>
        </label>
        <label className="field">
          <span>将通过系统文件选择器指定导出位置。</span>
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={exportIncludeDeleted}
            onChange={(e) => setExportIncludeDeleted(e.target.checked)}
          />
          包含已删除记录
        </label>
      </Modal>
    </div>
  );
}
