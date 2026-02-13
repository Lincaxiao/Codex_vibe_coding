from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import threading
from typing import Any

from .clock import RealClock
from .db import FocusLogDB, default_db_path, normalize_tags
from .exporting import export_sessions_csv
from .notifier import Notifier
from .reporting import build_stats, format_duration, generate_weekly_report
from .timer import PomodoroRunner, TimerConfig, format_countdown

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:
    tk = None
    ttk = None
    messagebox = None


class _NullStream:
    def write(self, _: str) -> None:
        return None

    def flush(self) -> None:
        return None


class FocusLogGUI:
    def __init__(self, db_path: Path) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("当前 Python 环境不可用 tkinter。")

        self.db_path = Path(db_path)
        self.db = FocusLogDB(self.db_path)
        self.out_dir = Path(__file__).resolve().parent / "out"

        self.root = tk.Tk()
        self.root.title("FocusLog")
        self.root.geometry("900x680")
        self.root.minsize(860, 640)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._event_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._runner: PomodoroRunner | None = None
        self._worker: threading.Thread | None = None
        self._closing = False

        self.task_var = tk.StringVar(value="")
        self.tags_var = tk.StringVar(value="")
        self.work_var = tk.StringVar(value="25")
        self.break_var = tk.StringVar(value="5")
        self.long_break_var = tk.StringVar(value="15")
        self.cycles_var = tk.StringVar(value="4")
        self.tick_var = tk.StringVar(value="1")
        self.notify_var = tk.BooleanVar(value=False)
        self.no_sound_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="空闲")
        self.countdown_var = tk.StringVar(value="00:00")
        self.stage_var = tk.StringVar(value="等待开始")

        self._build_layout()
        self._refresh_views()

        self.root.after(100, self._poll_runner_events)

    def run(self) -> None:
        self.root.mainloop()

    def _build_layout(self) -> None:
        frame_main = ttk.Frame(self.root, padding=12)
        frame_main.pack(fill=tk.BOTH, expand=True)

        frame_form = ttk.LabelFrame(frame_main, text="计时设置", padding=10)
        frame_form.pack(fill=tk.X)

        ttk.Label(frame_form, text="任务").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame_form, textvariable=self.task_var, width=28).grid(
            row=0, column=1, sticky="ew", padx=(6, 12)
        )

        ttk.Label(frame_form, text="标签(逗号分隔)").grid(row=0, column=2, sticky="w")
        ttk.Entry(frame_form, textvariable=self.tags_var, width=28).grid(
            row=0, column=3, sticky="ew", padx=(6, 0)
        )

        ttk.Label(frame_form, text="工作(分钟)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.work_var, width=10).grid(
            row=1, column=1, sticky="w", padx=(6, 12), pady=(8, 0)
        )

        ttk.Label(frame_form, text="短休息(分钟)").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.break_var, width=10).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=(8, 0)
        )

        ttk.Label(frame_form, text="长休息(分钟)").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.long_break_var, width=10).grid(
            row=2, column=1, sticky="w", padx=(6, 12), pady=(8, 0)
        )

        ttk.Label(frame_form, text="循环次数").grid(row=2, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.cycles_var, width=10).grid(
            row=2, column=3, sticky="w", padx=(6, 0), pady=(8, 0)
        )

        ttk.Label(frame_form, text="刷新间隔(秒)").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame_form, textvariable=self.tick_var, width=10).grid(
            row=3, column=1, sticky="w", padx=(6, 12), pady=(8, 0)
        )

        ttk.Checkbutton(frame_form, text="桌面通知", variable=self.notify_var).grid(
            row=3, column=2, sticky="w", pady=(8, 0)
        )
        ttk.Checkbutton(frame_form, text="禁用提示音", variable=self.no_sound_var).grid(
            row=3, column=3, sticky="w", pady=(8, 0)
        )

        for idx in range(4):
            frame_form.columnconfigure(idx, weight=1)

        frame_actions = ttk.Frame(frame_main)
        frame_actions.pack(fill=tk.X, pady=(10, 0))

        self.btn_start = ttk.Button(frame_actions, text="开始", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT)

        self.btn_stop = ttk.Button(frame_actions, text="停止", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(frame_actions, text="刷新统计", command=self._refresh_views).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_actions, text="导出 CSV", command=self._on_export).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(frame_actions, text="生成周报", command=self._on_report).pack(side=tk.LEFT, padx=(8, 0))

        frame_status = ttk.LabelFrame(frame_main, text="运行状态", padding=10)
        frame_status.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(frame_status, textvariable=self.stage_var, font=("Segoe UI", 12)).pack(anchor="w")
        ttk.Label(frame_status, textvariable=self.countdown_var, font=("Consolas", 28, "bold")).pack(anchor="w", pady=(6, 0))
        ttk.Label(frame_status, textvariable=self.status_var).pack(anchor="w", pady=(6, 0))

        frame_bottom = ttk.PanedWindow(frame_main, orient=tk.HORIZONTAL)
        frame_bottom.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        frame_stats = ttk.LabelFrame(frame_bottom, text="统计", padding=8)
        frame_logs = ttk.LabelFrame(frame_bottom, text="最近日志", padding=8)
        frame_bottom.add(frame_stats, weight=1)
        frame_bottom.add(frame_logs, weight=2)

        self.stats_text = tk.Text(frame_stats, height=18, wrap=tk.WORD)
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        self.logs_text = tk.Text(frame_logs, height=18, wrap=tk.NONE)
        self.logs_text.pack(fill=tk.BOTH, expand=True)

    def _on_start(self) -> None:
        if self._is_running():
            self.status_var.set("已有计时在运行。")
            return

        try:
            config = TimerConfig(
                task=self.task_var.get().strip(),
                tags=normalize_tags(self.tags_var.get()),
                work_minutes=self._parse_float(self.work_var.get(), "工作时长"),
                break_minutes=self._parse_float(self.break_var.get(), "短休息时长"),
                long_break_minutes=self._parse_float(self.long_break_var.get(), "长休息时长"),
                cycles=self._parse_int(self.cycles_var.get(), "循环次数", min_value=1),
                tick_seconds=self._parse_float(self.tick_var.get(), "刷新间隔", min_value=0),
                sound=not self.no_sound_var.get(),
                notify=self.notify_var.get(),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self._runner = PomodoroRunner(
            db=self.db,
            clock=RealClock(),
            notifier=Notifier(),
            stream=_NullStream(),
            progress_callback=self._push_event,
        )
        self._worker = threading.Thread(target=self._run_worker, args=(config,))
        self._worker.start()

        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.stage_var.set("准备开始")
        self.status_var.set("计时进行中")

    def _on_stop(self) -> None:
        if self._runner is None:
            return
        self._runner.request_stop()
        self.status_var.set("收到停止请求，正在结束当前片段...")
        self.btn_stop.config(state=tk.DISABLED)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._is_running():
            self._on_stop()
            self.status_var.set("正在安全退出：等待当前片段记录完成...")
            self.root.after(100, self._finish_close_if_idle)
            return
        self.root.destroy()

    def _finish_close_if_idle(self) -> None:
        if self._is_running():
            self.root.after(100, self._finish_close_if_idle)
            return
        self.root.destroy()

    def _on_export(self) -> None:
        csv_path = export_sessions_csv(self.db, self.out_dir)
        self.status_var.set(f"CSV 已导出：{csv_path}")

    def _on_report(self) -> None:
        report_path = generate_weekly_report(self.db, self.out_dir)
        self.status_var.set(f"周报已生成：{report_path}")

    def _run_worker(self, config: TimerConfig) -> None:
        if self._runner is None:
            return

        try:
            self._runner.run(config)
        except Exception as exc:
            self._push_event("runner_error", {"message": f"计时线程异常：{exc}"})

    def _push_event(self, event: str, payload: dict[str, Any]) -> None:
        self._event_queue.put((event, payload))

    def _poll_runner_events(self) -> None:
        try:
            while True:
                event, payload = self._event_queue.get_nowait()
                self._handle_event(event, payload)
        except queue.Empty:
            pass

        self.root.after(100, self._poll_runner_events)

    def _handle_event(self, event: str, payload: dict[str, Any]) -> None:
        if event == "tick":
            label = str(payload.get("label", ""))
            remaining_sec = int(payload.get("remaining_sec", 0))
            self.stage_var.set(label)
            self.countdown_var.set(format_countdown(remaining_sec))
            return

        if event == "interval_start":
            self.stage_var.set(str(payload.get("label", "")))
            duration = int(payload.get("duration_sec", 0))
            self.countdown_var.set(format_countdown(duration))
            return

        if event == "interval_end":
            kind = "工作" if payload.get("kind") == "work" else "休息"
            label = str(payload.get("label", ""))
            completed = bool(payload.get("completed", False))
            duration = int(payload.get("duration_sec", 0))
            state = "完成" if completed else f"中断({payload.get('interrupted_reason') or '未知'})"
            self.status_var.set(f"{kind}阶段 {label}：{state}，用时 {format_countdown(duration)}")
            self._refresh_views()
            return

        if event == "run_end":
            interrupted = bool(payload.get("interrupted", False))
            completed_work = int(payload.get("completed_work_sessions", 0))
            if interrupted:
                self.status_var.set(f"计时结束（中断），已完成工作会话 {completed_work} 次")
            else:
                self.status_var.set(f"计时完成，已完成工作会话 {completed_work} 次")
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.stage_var.set("空闲")
            self.countdown_var.set("00:00")
            self._runner = None
            self._worker = None
            self._refresh_views()
            if self._closing:
                self.root.after(0, self._finish_close_if_idle)
            return

        if event == "runner_error":
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self._runner = None
            self._worker = None
            self._show_error(str(payload.get("message", "未知错误")))
            if self._closing:
                self.root.after(0, self._finish_close_if_idle)

    def _refresh_views(self) -> None:
        self._refresh_stats()
        self._refresh_logs()

    def _refresh_stats(self) -> None:
        stats = build_stats(self.db)
        lines: list[str] = []
        for key, title in (
            ("today", "今天"),
            ("this_week", "本周"),
            ("last_7_days", "最近7天"),
        ):
            window = stats[key]
            lines.append(f"[{title}]")
            lines.append(f"工作时长：{format_duration(window.work_sec)}")
            lines.append(f"休息时长：{format_duration(window.break_sec)}")
            lines.append(f"工作会话：{window.work_sessions} 次")
            lines.append(f"完成工作会话：{window.completed_work_sessions} 次")
            lines.append(f"中断会话：{window.interrupted_sessions} 次")
            lines.append("")

        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete("1.0", tk.END)
        self.stats_text.insert(tk.END, "\n".join(lines).strip() + "\n")
        self.stats_text.config(state=tk.DISABLED)

    def _refresh_logs(self) -> None:
        sessions = self.db.list_sessions(limit=30)
        lines: list[str] = []
        for item in sessions:
            local_start = item.start_time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            kind = "工作" if item.kind == "work" else "休息"
            state = "完成" if item.completed else f"中断({item.interrupted_reason or '未知'})"
            task = item.task or "-"
            tags = item.tags or "-"
            lines.append(
                f"{local_start} | {kind} | {format_duration(item.duration_sec)} | {state} | 任务:{task} | 标签:{tags}"
            )

        if not lines:
            lines.append("暂无日志")

        self.logs_text.config(state=tk.NORMAL)
        self.logs_text.delete("1.0", tk.END)
        self.logs_text.insert(tk.END, "\n".join(lines) + "\n")
        self.logs_text.config(state=tk.DISABLED)

    def _is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _show_error(self, message: str) -> None:
        self.status_var.set(message)
        if messagebox is not None:
            messagebox.showerror("FocusLog", message)

    @staticmethod
    def _parse_float(text: str, field: str, min_value: float = 0.0) -> float:
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{field} 不是有效数字") from exc
        if value < min_value:
            raise ValueError(f"{field} 不能小于 {min_value}")
        return value

    @staticmethod
    def _parse_int(text: str, field: str, min_value: int = 0) -> int:
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{field} 不是有效整数") from exc
        if value < min_value:
            raise ValueError(f"{field} 不能小于 {min_value}")
        return value


def launch_gui(db_path: Path | None = None) -> int:
    path = Path(db_path or default_db_path())
    if tk is None or ttk is None:
        print("当前环境不支持 tkinter，无法启动 GUI。")
        return 2

    try:
        app = FocusLogGUI(path)
    except Exception as exc:
        print(f"GUI 启动失败：{exc}")
        return 2

    app.run()
    return 0
