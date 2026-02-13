from __future__ import annotations

import re
from pathlib import Path

from .db import PromptDB, PromptRecord, default_db_path, normalize_tags
from .service import copy_to_clipboard, parse_var_entries, render_template

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:
    tk = None
    ttk = None
    messagebox = None

# Legacy Tk GUI kept for rollback only.


class PromptVaultGUI:
    def __init__(self, db_path: Path) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("当前 Python 环境不可用 tkinter。")

        self.db = PromptDB(Path(db_path))
        self.db.init()

        self.root = tk.Tk()
        self.root.title("Prompt Vault")
        self.root.geometry("1080x700")
        self.root.minsize(980, 620)

        self.search_var = tk.StringVar(value="")
        self.include_deleted_var = tk.BooleanVar(value=False)
        self.id_var = tk.StringVar(value="(新建)")
        self.title_var = tk.StringVar(value="")
        self.tags_var = tk.StringVar(value="")
        self.render_vars_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="就绪")

        self.current_prompt_id: int | None = None
        self._list_ids: list[int] = []

        self._build_layout()
        self._refresh_list()

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.pack(fill=tk.BOTH, expand=True)

        frame_top = ttk.Frame(root_frame)
        frame_top.pack(fill=tk.X)

        ttk.Label(frame_top, text="搜索").pack(side=tk.LEFT)
        search_entry = ttk.Entry(frame_top, textvariable=self.search_var, width=42)
        search_entry.pack(side=tk.LEFT, padx=(6, 8))
        search_entry.bind("<Return>", lambda _: self._on_search())
        ttk.Button(frame_top, text="搜索", command=self._on_search).pack(side=tk.LEFT)
        ttk.Button(frame_top, text="清空", command=self._on_clear_search).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(frame_top, text="包含已删除", variable=self.include_deleted_var, command=self._refresh_list).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        pane = ttk.PanedWindow(root_frame, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        frame_left = ttk.LabelFrame(pane, text="提示词列表", padding=8)
        frame_right = ttk.LabelFrame(pane, text="详情编辑", padding=8)
        pane.add(frame_left, weight=1)
        pane.add(frame_right, weight=2)

        self.listbox = tk.Listbox(frame_left, exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select_prompt)

        scroll = ttk.Scrollbar(frame_left, orient=tk.VERTICAL, command=self.listbox.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scroll.set)

        frame_form = ttk.Frame(frame_right)
        frame_form.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame_form, text="ID").grid(row=0, column=0, sticky="w")
        ttk.Label(frame_form, textvariable=self.id_var).grid(row=0, column=1, sticky="w")

        ttk.Label(frame_form, text="标题").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.title_var).grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame_form, text="标签（逗号分隔）").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.tags_var).grid(row=2, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame_form, text="正文").grid(row=3, column=0, sticky="nw", pady=(8, 0))
        self.body_text = tk.Text(frame_form, height=14, wrap=tk.WORD)
        self.body_text.grid(row=3, column=1, sticky="nsew", pady=(8, 0))

        ttk.Label(frame_form, text="渲染变量（示例: name=张三;date=2026-02-13）").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Entry(frame_form, textvariable=self.render_vars_var).grid(row=4, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame_form, text="渲染预览").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        self.render_text = tk.Text(frame_form, height=9, wrap=tk.WORD)
        self.render_text.grid(row=5, column=1, sticky="nsew", pady=(8, 0))

        frame_actions = ttk.Frame(frame_form)
        frame_actions.grid(row=6, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(frame_actions, text="新建", command=self._on_new).pack(side=tk.LEFT)
        ttk.Button(frame_actions, text="保存", command=self._on_save).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_actions, text="软删除", command=self._on_delete).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_actions, text="渲染", command=self._on_render).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_actions, text="复制渲染结果", command=self._on_copy_render).pack(side=tk.LEFT, padx=(8, 0))

        frame_form.columnconfigure(1, weight=1)
        frame_form.rowconfigure(3, weight=3)
        frame_form.rowconfigure(5, weight=2)

        ttk.Label(root_frame, textvariable=self.status_var).pack(anchor="w", pady=(8, 0))

    def _on_search(self) -> None:
        self._refresh_list()

    def _on_clear_search(self) -> None:
        self.search_var.set("")
        self._refresh_list()

    def _on_select_prompt(self, _: object) -> None:
        selected = self.listbox.curselection()
        if not selected:
            return
        idx = int(selected[0])
        if idx < 0 or idx >= len(self._list_ids):
            return
        prompt_id = self._list_ids[idx]
        rec = self.db.get_prompt(prompt_id)
        if rec is None:
            self._set_status("提示词不存在，可能已被删除。")
            self._refresh_list()
            return
        self._load_record(rec)

    def _on_new(self) -> None:
        self.current_prompt_id = None
        self.id_var.set("(新建)")
        self.title_var.set("")
        self.tags_var.set("")
        self.body_text.delete("1.0", tk.END)
        self.render_vars_var.set("")
        self.render_text.delete("1.0", tk.END)
        self._set_status("已切换到新建模式。")

    def _on_save(self) -> None:
        title = self.title_var.get()
        body = self.body_text.get("1.0", tk.END).rstrip("\n")
        tags = self._parse_tags(self.tags_var.get())
        try:
            if self.current_prompt_id is None:
                prompt_id = self.db.add_prompt(title=title, body=body)
                if tags:
                    self.db.set_tags(prompt_id, tags)
                self._set_status(f"已新增提示词 ID={prompt_id}")
                self._refresh_list(select_id=prompt_id)
                return

            ok = self.db.update_prompt(self.current_prompt_id, title=title, body=body)
            if not ok:
                self._set_status("保存失败：提示词不存在。")
                self._refresh_list()
                return
            self._sync_tags(self.current_prompt_id, tags)
            self._set_status(f"已更新提示词 ID={self.current_prompt_id}")
            self._refresh_list(select_id=self.current_prompt_id)
        except ValueError as exc:
            self._show_error(str(exc))

    def _on_delete(self) -> None:
        if self.current_prompt_id is None:
            self._show_error("请先选择一个提示词。")
            return
        if messagebox is not None:
            if not messagebox.askyesno("Prompt Vault", "确认软删除当前提示词吗？"):
                return
        if self.db.soft_delete(self.current_prompt_id):
            deleted_id = self.current_prompt_id
            self._on_new()
            self._refresh_list()
            self._set_status(f"已软删除 ID={deleted_id}")
            return
        self._show_error("软删除失败：提示词不存在。")

    def _on_render(self) -> None:
        body = self.body_text.get("1.0", tk.END).rstrip("\n")
        entries = [item.strip() for item in re.split(r"[;\n]", self.render_vars_var.get()) if item.strip()]
        try:
            variables = parse_var_entries(entries)
            rendered = render_template(body, variables)
        except ValueError as exc:
            self._show_error(str(exc))
            return
        self.render_text.delete("1.0", tk.END)
        self.render_text.insert(tk.END, rendered)
        self._set_status("渲染完成。")

    def _on_copy_render(self) -> None:
        content = self.render_text.get("1.0", tk.END).rstrip("\n")
        if not content:
            self._show_error("没有可复制的渲染结果。")
            return
        if copy_to_clipboard(content):
            self._set_status("渲染结果已复制到剪贴板。")
            return
        self._show_error("剪贴板不可用，请手动复制。")

    def _refresh_list(self, select_id: int | None = None) -> None:
        query = self.search_var.get().strip()
        include_deleted = self.include_deleted_var.get()
        records = self.db.search(query, include_deleted=include_deleted) if query else self.db.list_prompts(include_deleted)

        self.listbox.delete(0, tk.END)
        self._list_ids = []
        for rec in records:
            status = "deleted" if rec.is_deleted else "active"
            self.listbox.insert(tk.END, f"{rec.id:>4} | {status:<7} | {rec.title}")
            self._list_ids.append(rec.id)

        if not records:
            self._set_status("当前没有匹配提示词。")
            return

        selected_idx = 0
        if select_id is not None and select_id in self._list_ids:
            selected_idx = self._list_ids.index(select_id)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(selected_idx)
        self.listbox.activate(selected_idx)
        self._load_record(records[selected_idx])

    def _load_record(self, rec: PromptRecord) -> None:
        self.current_prompt_id = rec.id
        self.id_var.set(str(rec.id))
        self.title_var.set(rec.title)
        self.tags_var.set(", ".join(self.db.get_tags(rec.id)))
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert(tk.END, rec.body)
        self.render_text.delete("1.0", tk.END)
        self._set_status(f"已加载 ID={rec.id}")

    def _sync_tags(self, prompt_id: int, desired_tags: list[str]) -> None:
        current = set(self.db.get_tags(prompt_id))
        desired = set(desired_tags)
        to_add = sorted(desired - current)
        to_remove = sorted(current - desired)
        if to_add:
            self.db.set_tags(prompt_id, to_add)
        if to_remove:
            self.db.remove_tags(prompt_id, to_remove)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _show_error(self, text: str) -> None:
        self._set_status(text)
        if messagebox is not None:
            messagebox.showerror("Prompt Vault", text)

    @staticmethod
    def _parse_tags(text: str) -> list[str]:
        parts = re.split(r"[,，\n]", text)
        return normalize_tags(parts)


def launch_gui(db_path: Path | None = None) -> int:
    path = Path(db_path or default_db_path())
    if tk is None or ttk is None:
        print("当前环境不支持 tkinter，无法启动 GUI。")
        return 2

    try:
        app = PromptVaultGUI(path)
    except Exception as exc:
        print(f"GUI 启动失败：{exc}")
        return 2

    app.run()
    return 0
