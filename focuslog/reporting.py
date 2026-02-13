from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .db import FocusLogDB, StoredSession


@dataclass(frozen=True)
class StatsWindow:
    work_sec: int
    break_sec: int
    work_sessions: int
    completed_work_sessions: int
    interrupted_sessions: int


def format_duration(seconds: int) -> str:
    total = max(0, int(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}小时{minutes:02d}分{sec:02d}秒"
    return f"{minutes}分{sec:02d}秒"


def build_stats(db: FocusLogDB, now: datetime | None = None) -> dict[str, StatsWindow]:
    ref = now or datetime.now().astimezone()
    if ref.tzinfo is None:
        ref = ref.astimezone()

    today_start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    last7_start = ref - timedelta(days=7)

    return {
        "today": _collect_window(db.list_sessions_between(today_start, ref)),
        "this_week": _collect_window(db.list_sessions_between(week_start, ref)),
        "last_7_days": _collect_window(db.list_sessions_between(last7_start, ref)),
    }


def generate_weekly_report(
    db: FocusLogDB,
    out_dir: Path,
    year: int | None = None,
    week: int | None = None,
    now: datetime | None = None,
) -> Path:
    ref = now or datetime.now().astimezone()
    if ref.tzinfo is None:
        ref = ref.astimezone()

    iso = ref.isocalendar()
    target_year = int(year or iso.year)
    target_week = int(week or iso.week)
    tz = ref.tzinfo

    week_start = datetime.fromisocalendar(target_year, target_week, 1).replace(tzinfo=tz)
    week_end = week_start + timedelta(days=7)
    sessions = db.list_sessions_between(week_start, week_end)

    stats = _collect_window(sessions)
    task_totals: dict[str, int] = {}
    tag_totals: dict[str, int] = {}
    day_totals: dict[str, int] = {}

    for item in sessions:
        if item.kind != "work":
            continue

        task_name = item.task.strip() or "未命名任务"
        task_totals[task_name] = task_totals.get(task_name, 0) + item.duration_sec

        local_day = item.start_time.astimezone(tz).strftime("%Y-%m-%d")
        day_totals[local_day] = day_totals.get(local_day, 0) + item.duration_sec

        for tag in [x.strip() for x in item.tags.split(",") if x.strip()]:
            tag_totals[tag] = tag_totals.get(tag, 0) + item.duration_sec

    lines: list[str] = []
    lines.append(f"# FocusLog 周报 {target_year}-W{target_week:02d}")
    lines.append("")
    lines.append(f"- 统计区间：{week_start.strftime('%Y-%m-%d')} 至 {(week_end - timedelta(days=1)).strftime('%Y-%m-%d')}")
    lines.append(f"- 生成时间：{ref.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    lines.append("")

    lines.append("## 总览")
    lines.append(f"- 工作总时长：{format_duration(stats.work_sec)}")
    lines.append(f"- 休息总时长：{format_duration(stats.break_sec)}")
    lines.append(f"- 工作会话：{stats.work_sessions} 次")
    lines.append(f"- 完成工作会话：{stats.completed_work_sessions} 次")
    lines.append(f"- 中断会话：{stats.interrupted_sessions} 次")
    lines.append("")

    lines.append("## 任务分布")
    if task_totals:
        lines.append("| 任务 | 时长 |")
        lines.append("| --- | --- |")
        for task_name, sec in sorted(task_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {task_name} | {format_duration(sec)} |")
    else:
        lines.append("本周暂无工作会话。")
    lines.append("")

    lines.append("## 标签分布")
    if tag_totals:
        lines.append("| 标签 | 时长 |")
        lines.append("| --- | --- |")
        for tag_name, sec in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {tag_name} | {format_duration(sec)} |")
    else:
        lines.append("本周无标签数据。")
    lines.append("")

    lines.append("## 每日工作时长")
    if day_totals:
        lines.append("| 日期 | 时长 |")
        lines.append("| --- | --- |")
        for day, sec in sorted(day_totals.items()):
            lines.append(f"| {day} | {format_duration(sec)} |")
    else:
        lines.append("本周暂无每日数据。")
    lines.append("")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"week-{target_year}-{target_week:02d}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _collect_window(sessions: list[StoredSession]) -> StatsWindow:
    work_sec = 0
    break_sec = 0
    work_sessions = 0
    completed_work_sessions = 0
    interrupted_sessions = 0

    for item in sessions:
        if item.kind == "work":
            work_sec += item.duration_sec
            work_sessions += 1
            if item.completed:
                completed_work_sessions += 1
        else:
            break_sec += item.duration_sec

        if not item.completed:
            interrupted_sessions += 1

    return StatsWindow(
        work_sec=work_sec,
        break_sec=break_sec,
        work_sessions=work_sessions,
        completed_work_sessions=completed_work_sessions,
        interrupted_sessions=interrupted_sessions,
    )
