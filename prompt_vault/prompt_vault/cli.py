from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .db import PromptDB, default_db_path
from .service import (
    copy_to_clipboard,
    export_json,
    export_markdown,
    format_prompt,
    import_json,
    load_json_vars,
    parse_var_entries,
    render_template,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m prompt_vault", description="Prompt Vault 本地提示词管理器")
    parser.add_argument("--db", default=str(default_db_path()), help="SQLite 数据库路径")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="初始化数据库")

    p_add = sub.add_parser("add", help="添加提示词")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--body", required=True)

    p_list = sub.add_parser("list", help="列出提示词")
    p_list.add_argument("--all", action="store_true", help="包含软删除记录")

    p_show = sub.add_parser("show", help="显示提示词详情")
    p_show.add_argument("id", type=int)

    p_search = sub.add_parser("search", help="搜索标题、正文和标签")
    p_search.add_argument("query")
    p_search.add_argument("--all", action="store_true")

    p_edit = sub.add_parser("edit", help="编辑提示词")
    p_edit.add_argument("id", type=int)
    p_edit.add_argument("--title")
    p_edit.add_argument("--body")

    p_delete = sub.add_parser("delete", help="软删除提示词")
    p_delete.add_argument("id", type=int)

    p_tag = sub.add_parser("tag", help="管理标签")
    p_tag.add_argument("id", type=int)
    p_tag.add_argument("--add", action="append", default=[])
    p_tag.add_argument("--remove", action="append", default=[])

    p_export = sub.add_parser("export", help="导出提示词")
    p_export.add_argument("--format", choices=["json", "markdown"], required=True)
    p_export.add_argument("--output", required=True)
    p_export.add_argument("--all", action="store_true")

    p_import = sub.add_parser("import", help="从 JSON 导入提示词")
    p_import.add_argument("--input", required=True)

    p_render = sub.add_parser("render", help="渲染模板变量")
    p_render.add_argument("id", type=int)
    p_render.add_argument("--var", action="append", default=[])
    p_render.add_argument("--vars-json")

    p_clip = sub.add_parser("clip", help="复制提示词到剪贴板")
    p_clip.add_argument("id", type=int)
    p_clip.add_argument("--var", action="append", default=[])
    p_clip.add_argument("--vars-json")

    sub.add_parser("gui", help="启动图形界面")

    return parser


def ensure_db_for_read(db: PromptDB) -> None:
    if not db.path.exists():
        db.init()
        print(f"提示: 数据库不存在，已自动创建: {db.path}", file=sys.stderr)


def command_init(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    print(f"数据库已初始化: {db.path}")
    return 0


def command_add(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    try:
        prompt_id = db.add_prompt(title=args.title, body=args.body)
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 1
    print(f"已添加提示词，ID={prompt_id}")
    return 0


def command_list(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    records = db.list_prompts(include_deleted=args.all)
    for rec in records:
        status = "deleted" if rec.is_deleted else "active"
        print(f"{rec.id}\t{status}\t{rec.title}")
    print(f"总计: {len(records)}")
    return 0


def command_show(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    rec = db.get_prompt(args.id)
    if not rec:
        print("未找到该提示词", file=sys.stderr)
        return 1
    print(format_prompt(rec, db.get_tags(rec.id)))
    return 0


def command_search(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    records = db.search(args.query, include_deleted=args.all)
    for rec in records:
        tags = ",".join(db.get_tags(rec.id))
        print(f"{rec.id}\t{rec.title}\t[{tags}]")
    print(f"命中: {len(records)}")
    return 0


def command_edit(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    if args.title is None and args.body is None:
        print("请至少提供 --title 或 --body", file=sys.stderr)
        return 1
    try:
        ok = db.update_prompt(args.id, title=args.title, body=args.body)
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 1
    if not ok:
        print("未找到该提示词", file=sys.stderr)
        return 1
    print("已更新")
    return 0


def command_delete(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    if not db.soft_delete(args.id):
        print("未找到该提示词", file=sys.stderr)
        return 1
    print("已软删除")
    return 0


def command_tag(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    if not db.get_prompt(args.id):
        print("未找到该提示词", file=sys.stderr)
        return 1
    add_tags = sorted({t.strip() for t in args.add if t.strip()})
    remove_tags = sorted({t.strip() for t in args.remove if t.strip()})
    if add_tags:
        db.set_tags(args.id, add_tags)
    if remove_tags:
        db.remove_tags(args.id, remove_tags)
    print(f"标签: {', '.join(db.get_tags(args.id)) or '(无标签)'}")
    return 0


def merge_vars(args: argparse.Namespace) -> dict[str, str]:
    vars_data: dict[str, str] = {}
    vars_data.update(load_json_vars(args.vars_json))
    vars_data.update(parse_var_entries(args.var))
    return vars_data


def get_body_or_error(db: PromptDB, prompt_id: int) -> str:
    rec = db.get_prompt(prompt_id)
    if not rec:
        raise ValueError("未找到该提示词")
    return rec.body


def command_render(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    try:
        body = get_body_or_error(db, args.id)
        rendered = render_template(body, merge_vars(args))
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 1
    print(rendered)
    return 0


def command_clip(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    try:
        body = get_body_or_error(db, args.id)
        content = render_template(body, merge_vars(args))
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 1
    if copy_to_clipboard(content):
        print("已复制到剪贴板")
    else:
        print("警告: 未找到可用剪贴板命令，已输出到标准输出", file=sys.stderr)
        print(content)
    return 0


def command_export(db: PromptDB, args: argparse.Namespace) -> int:
    ensure_db_for_read(db)
    output = Path(args.output)
    if args.format == "json":
        export_json(db, output, include_deleted=args.all)
    else:
        export_markdown(db, output, include_deleted=args.all)
    print(f"导出完成: {output}")
    return 0


def command_import(db: PromptDB, args: argparse.Namespace) -> int:
    db.init()
    path = Path(args.input)
    if not path.exists():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 1
    try:
        added, skipped = import_json(db, path)
    except (json.JSONDecodeError, ValueError) as err:
        print(f"导入失败: {err}", file=sys.stderr)
        return 1
    print(f"导入完成: 新增 {added}，跳过 {skipped}")
    return 0


def command_gui(db: PromptDB, args: argparse.Namespace) -> int:
    from .gui import launch_gui

    return launch_gui(db.path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    db = PromptDB(Path(args.db))

    dispatch = {
        "init": command_init,
        "add": command_add,
        "list": command_list,
        "show": command_show,
        "search": command_search,
        "edit": command_edit,
        "delete": command_delete,
        "tag": command_tag,
        "export": command_export,
        "import": command_import,
        "render": command_render,
        "clip": command_clip,
        "gui": command_gui,
    }
    return dispatch[args.command](db, args)
