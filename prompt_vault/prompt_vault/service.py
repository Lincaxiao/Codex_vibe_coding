from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .db import PromptDB, PromptRecord, compute_hash


PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_\-]+)\s*\}\}")


def render_template(template: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return PLACEHOLDER.sub(replace, template)


def parse_var_entries(entries: Iterable[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"无效变量格式: {entry}，应为 key=value")
        key, value = entry.split("=", 1)
        if not key.strip():
            raise ValueError(f"变量键不能为空: {entry}")
        values[key.strip()] = value
    return values


def load_json_vars(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    content = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError("JSON 变量文件必须是对象")
    result: dict[str, str] = {}
    for key, value in content.items():
        result[str(key)] = str(value)
    return result


def export_json(db: PromptDB, output_path: Path, include_deleted: bool = False) -> None:
    records = db.list_prompts(include_deleted=include_deleted)
    payload = []
    for record in records:
        payload.append(
            {
                "id": record.id,
                "title": record.title,
                "body": record.body,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "is_deleted": bool(record.is_deleted),
                "tags": db.get_tags(record.id),
                "content_hash": compute_hash(record.title, record.body),
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_markdown(db: PromptDB, output_path: Path, include_deleted: bool = False) -> None:
    records = db.list_prompts(include_deleted=include_deleted)
    lines = ["# Prompt Vault 导出", ""]
    for rec in records:
        tags = ", ".join(db.get_tags(rec.id)) or "(无标签)"
        lines.extend(
            [
                f"## [{rec.id}] {rec.title}",
                f"- 创建时间: {rec.created_at}",
                f"- 更新时间: {rec.updated_at}",
                f"- 已删除: {bool(rec.is_deleted)}",
                f"- 标签: {tags}",
                "",
                "```text",
                rec.body,
                "```",
                "",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def import_json(db: PromptDB, input_path: Path) -> tuple[int, int]:
    content = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(content, list):
        raise ValueError("导入 JSON 必须是数组")
    added = 0
    skipped = 0
    for item in content:
        if not isinstance(item, dict):
            skipped += 1
            continue
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", ""))
        if not title or not body:
            skipped += 1
            continue
        content_hash = compute_hash(title, body)
        if db.get_by_hash(content_hash):
            skipped += 1
            continue
        created_at = item.get("created_at")
        prompt_id = db.add_prompt(title=title, body=body, created_at=created_at)
        tags = item.get("tags") or []
        if isinstance(tags, list):
            db.set_tags(prompt_id, [str(t) for t in tags])
        if item.get("is_deleted"):
            db.soft_delete(prompt_id)
        added += 1
    return added, skipped


def copy_to_clipboard(text: str) -> bool:
    if _copy_with_tkinter(text):
        return True

    commands: list[tuple[list[str], bool]] = [
        (["pbcopy"], False),
        (["wl-copy"], False),
        (["xclip", "-selection", "clipboard"], False),
        (["clip"], True),
    ]
    for cmd in commands:
        args, as_text = cmd
        if shutil.which(args[0]):
            try:
                if as_text:
                    subprocess.run(args, input=text, text=True, check=True)
                else:
                    subprocess.run(args, input=text.encode("utf-8"), check=True)
                return True
            except Exception:
                continue
    return False


def _copy_with_tkinter(text: str) -> bool:
    # Tkinter clipboard supports Unicode and avoids shell quoting issues.
    try:
        import tkinter as tk
    except Exception:
        return False

    if os.environ.get("DISPLAY", "") == "" and os.name != "nt":
        return False

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        return True
    except Exception:
        return False
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def format_prompt(rec: PromptRecord, tags: list[str]) -> str:
    tags_line = ", ".join(tags) if tags else "(无标签)"
    return (
        f"ID: {rec.id}\n"
        f"标题: {rec.title}\n"
        f"创建时间: {rec.created_at}\n"
        f"更新时间: {rec.updated_at}\n"
        f"已删除: {bool(rec.is_deleted)}\n"
        f"标签: {tags_line}\n"
        "---\n"
        f"{rec.body}"
    )
