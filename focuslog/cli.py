from __future__ import annotations

import argparse
from datetime import date, datetime, time as dtime
from pathlib import Path
import sys

from .clock import RealClock
from .db import FocusLogDB, default_db_path, normalize_tags
from .exporting import export_sessions_csv
from .desktop import launch_desktop
from .gui import launch_gui
from .notifier import Notifier
from .reporting import build_stats, format_duration, generate_weekly_report
from .timer import PomodoroRunner, TimerConfig


DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "out"


def parse_since(value: str) -> datetime:
    text = value.strip()
    local_tz = datetime.now().astimezone().tzinfo
    if local_tz is None:
        raise argparse.ArgumentTypeError("无法识别本地时区")

    try:
        if len(text) == 10:
            day = date.fromisoformat(text)
            return datetime.combine(day, dtime.min).replace(tzinfo=local_tz)

        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        return dt
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--since 格式错误：{value}，请使用 YYYY-MM-DD 或 ISO 日期时间"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="focuslog",
        description="FocusLog：离线优先的命令行番茄钟、日志与周报工具",
    )
    parser.add_argument(
        "--db",
        default=str(default_db_path()),
        help="SQLite 数据库路径（默认在 focuslog/data/focuslog.sqlite）",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="开始番茄钟")
    start_parser.add_argument("--task", default="", help="任务名称")
    start_parser.add_argument("--tags", default="", help="标签，逗号分隔")
    start_parser.add_argument("--work", type=float, default=25.0, help="工作时长（分钟）")
    start_parser.add_argument(
        "--break",
        dest="break_minutes",
        type=float,
        default=5.0,
        help="短休息时长（分钟）",
    )
    start_parser.add_argument(
        "--long-break",
        dest="long_break_minutes",
        type=float,
        default=15.0,
        help="长休息时长（分钟）",
    )
    start_parser.add_argument("--cycles", type=int, default=4, help="循环次数")
    start_parser.add_argument(
        "--tick-seconds",
        type=float,
        default=1.0,
        help="倒计时刷新间隔（秒，>=0）",
    )
    start_parser.add_argument("--no-sound", action="store_true", help="禁用提示音")
    start_parser.add_argument("--notify", action="store_true", help="启用桌面通知")

    log_parser = subparsers.add_parser("log", help="查看日志")
    log_parser.add_argument("--since", type=parse_since, default=None, help="起始时间")
    log_parser.add_argument("--tag", default=None, help="按标签过滤")
    log_parser.add_argument("--task-contains", default=None, help="任务包含关键词")
    log_parser.add_argument("--limit", type=int, default=20, help="最多显示条数")

    subparsers.add_parser("stats", help="查看统计")

    report_parser = subparsers.add_parser("report", help="生成周报 Markdown")
    report_parser.add_argument("--year", type=int, default=None, help="ISO 年")
    report_parser.add_argument("--week", type=int, default=None, help="ISO 周")
    report_parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录，默认 focuslog/out",
    )

    export_parser = subparsers.add_parser("export", help="导出 CSV")
    export_parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录，默认 focuslog/out",
    )

    subparsers.add_parser("gui", help="启动图形界面")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gui":
        return _handle_gui(args)

    db = FocusLogDB(Path(args.db))

    if args.command == "start":
        return _handle_start(args, db, parser)
    if args.command == "log":
        return _handle_log(args, db)
    if args.command == "stats":
        return _handle_stats(db)
    if args.command == "report":
        return _handle_report(args, db)
    if args.command == "export":
        return _handle_export(args, db)

    parser.print_help()
    return 2


def _handle_start(args: argparse.Namespace, db: FocusLogDB, parser: argparse.ArgumentParser) -> int:
    if args.cycles < 1:
        parser.error("--cycles 必须大于等于 1")
    if args.work < 0 or args.break_minutes < 0 or args.long_break_minutes < 0:
        parser.error("时长参数不能为负数")
    if args.tick_seconds < 0:
        parser.error("--tick-seconds 不能为负数")

    config = TimerConfig(
        task=args.task.strip(),
        tags=normalize_tags(args.tags),
        work_minutes=float(args.work),
        break_minutes=float(args.break_minutes),
        long_break_minutes=float(args.long_break_minutes),
        cycles=int(args.cycles),
        tick_seconds=float(args.tick_seconds),
        sound=not bool(args.no_sound),
        notify=bool(args.notify),
    )

    runner = PomodoroRunner(db=db, clock=RealClock(), notifier=Notifier(stream=sys.stdout))
    result = runner.run(config)
    return 130 if result.interrupted else 0


def _handle_log(args: argparse.Namespace, db: FocusLogDB) -> int:
    sessions = db.list_sessions(
        since=args.since,
        tag=(args.tag.strip().lower() if args.tag else None),
        task_contains=(args.task_contains.strip() if args.task_contains else None),
        limit=args.limit,
    )

    if not sessions:
        print("没有匹配记录。")
        return 0

    for item in sessions:
        start_text = item.start_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
        kind_text = "工作" if item.kind == "work" else "休息"
        state_text = "完成" if item.completed else f"中断({item.interrupted_reason or '未知'})"
        task_text = item.task or "-"
        tags_text = item.tags or "-"
        print(
            f"{start_text} | {kind_text} | {format_duration(item.duration_sec)} | "
            f"{state_text} | 任务: {task_text} | 标签: {tags_text}"
        )
    return 0


def _handle_stats(db: FocusLogDB) -> int:
    stats = build_stats(db)
    mapping = [
        ("today", "今天"),
        ("this_week", "本周"),
        ("last_7_days", "最近 7 天"),
    ]

    for key, title in mapping:
        window = stats[key]
        print(f"[{title}]")
        print(f"工作时长: {format_duration(window.work_sec)}")
        print(f"休息时长: {format_duration(window.break_sec)}")
        print(f"工作会话: {window.work_sessions} 次")
        print(f"完成工作会话: {window.completed_work_sessions} 次")
        print(f"中断会话: {window.interrupted_sessions} 次")
        print("")
    return 0


def _handle_report(args: argparse.Namespace, db: FocusLogDB) -> int:
    out_dir = Path(args.out_dir)
    report_path = generate_weekly_report(
        db=db,
        out_dir=out_dir,
        year=args.year,
        week=args.week,
    )
    print(f"周报已生成：{report_path}")
    return 0


def _handle_export(args: argparse.Namespace, db: FocusLogDB) -> int:
    out_dir = Path(args.out_dir)
    csv_path = export_sessions_csv(db=db, out_dir=out_dir)
    print(f"CSV 已导出：{csv_path}")
    return 0


def _handle_gui(args: argparse.Namespace) -> int:
    result = launch_desktop(Path(args.db))
    if result == 0:
        return 0
    print("回退到 Tk GUI...")
    return launch_gui(Path(args.db))
