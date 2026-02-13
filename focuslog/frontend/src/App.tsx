import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import {
  exportCsv,
  generateWeeklyReport,
  getMeta,
  getStats,
  getTimerState,
  listSessions,
  startTimer,
  stopTimer
} from "./api";
import type { StatsResponse, TimerStartRequest, TimerState, TimerStreamEvent } from "./types";
import { formatCountdown, formatDateTime, formatDuration, parseNumberOrNull } from "./utils";

type ToastLevel = "success" | "error" | "info";
type ViewTab = "settings" | "timer" | "stats" | "sessions";

type ToastItem = {
  id: number;
  level: ToastLevel;
  text: string;
};

type TimerFormValues = TimerStartRequest;

type SessionsFilter = {
  since: string;
  tag: string;
  taskContains: string;
  limit: number;
};

type SessionsDraft = {
  since: string;
  tag: string;
  taskContains: string;
  limit: string;
};

type TimerPreset = {
  label: string;
  work: number;
  break: number;
  longBreak: number;
  cycles: number;
};

const DEFAULT_TIMER_VALUES: TimerFormValues = {
  task: "",
  tags: "",
  work_minutes: 25,
  break_minutes: 5,
  long_break_minutes: 15,
  cycles: 4,
  tick_seconds: 1,
  sound: true,
  notify: false
};

const DEFAULT_STATS: StatsResponse = {
  today: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 },
  this_week: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 },
  last_7_days: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 }
};

const DEFAULT_SESSIONS_DRAFT: SessionsDraft = {
  since: "",
  tag: "",
  taskContains: "",
  limit: "60"
};

const DEFAULT_SESSIONS_FILTER: SessionsFilter = {
  since: "",
  tag: "",
  taskContains: "",
  limit: 60
};

const TIMER_FORM_STORAGE_KEY = "focuslog.timer.form.v1";
const SESSIONS_FILTER_STORAGE_KEY = "focuslog.sessions.filter.v1";
const OUTPUT_FORM_STORAGE_KEY = "focuslog.output.form.v1";

const TIMER_PRESETS: TimerPreset[] = [
  { label: "经典 25/5", work: 25, break: 5, longBreak: 15, cycles: 4 },
  { label: "深度 50/10", work: 50, break: 10, longBreak: 20, cycles: 2 },
  { label: "冲刺 90/15", work: 90, break: 15, longBreak: 25, cycles: 1 }
];

function statusText(status: string): string {
  if (status === "running") return "运行中";
  if (status === "stopping") return "停止中";
  if (status === "error") return "异常";
  return "空闲";
}

function statusClass(status: string): string {
  if (status === "running") return "badge badge-running";
  if (status === "stopping") return "badge badge-stopping";
  if (status === "error") return "badge badge-error";
  return "badge badge-idle";
}

function ActionRow({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}

function StatCard({ title, stats }: { title: string; stats: StatsResponse["today"] }) {
  return (
    <div className="stat-card">
      <div className="stat-title">{title}</div>
      <div className="stat-line">工作时长：{formatDuration(stats.work_sec)}</div>
      <div className="stat-line">休息时长：{formatDuration(stats.break_sec)}</div>
      <div className="stat-line">工作会话：{stats.work_sessions}</div>
      <div className="stat-line">完成工作会话：{stats.completed_work_sessions}</div>
      <div className="stat-line">中断会话：{stats.interrupted_sessions}</div>
    </div>
  );
}

function TabButton({ active, onClick, text }: { active: boolean; onClick: () => void; text: string }) {
  return (
    <button className={`tab-btn ${active ? "tab-btn-active" : ""}`} type="button" onClick={onClick}>
      {text}
    </button>
  );
}

function sanitizeTimerValues(input: Partial<TimerFormValues>): TimerFormValues {
  const toNumber = (value: unknown, fallback: number) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    task: String(input.task ?? DEFAULT_TIMER_VALUES.task),
    tags: String(input.tags ?? DEFAULT_TIMER_VALUES.tags),
    work_minutes: Math.max(0, toNumber(input.work_minutes, DEFAULT_TIMER_VALUES.work_minutes)),
    break_minutes: Math.max(0, toNumber(input.break_minutes, DEFAULT_TIMER_VALUES.break_minutes)),
    long_break_minutes: Math.max(0, toNumber(input.long_break_minutes, DEFAULT_TIMER_VALUES.long_break_minutes)),
    cycles: Math.max(1, Math.floor(toNumber(input.cycles, DEFAULT_TIMER_VALUES.cycles))),
    tick_seconds: Math.max(0, toNumber(input.tick_seconds, DEFAULT_TIMER_VALUES.tick_seconds)),
    sound: input.sound !== false,
    notify: Boolean(input.notify)
  };
}

function summarizeLastEvent(state: TimerState | null | undefined): string {
  const eventName = String(state?.last_event?.event ?? "");
  if (!eventName) return "暂无事件";
  if (eventName === "tick") {
    const label = String(state?.last_event?.label ?? "");
    const remaining = Number(state?.last_event?.remaining_sec ?? 0);
    return `${label} · 剩余 ${formatCountdown(remaining)}`;
  }
  if (eventName === "interval_end") {
    const label = String(state?.last_event?.label ?? "");
    const completed = Boolean(state?.last_event?.completed);
    return `${label} · ${completed ? "完成" : "中断"}`;
  }
  if (eventName === "run_end") {
    const interrupted = Boolean(state?.last_event?.interrupted);
    return interrupted ? "本轮计时结束（中断）" : "本轮计时完成";
  }
  return eventName;
}

export default function App() {
  const queryClient = useQueryClient();
  const streamRef = useRef<EventSource | null>(null);

  const [activeTab, setActiveTab] = useState<ViewTab>("timer");
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [statusLine, setStatusLine] = useState("就绪");
  const [intervalTotalSec, setIntervalTotalSec] = useState(0);

  const [sessionsDraft, setSessionsDraft] = useState<SessionsDraft>(DEFAULT_SESSIONS_DRAFT);
  const [sessionsFilter, setSessionsFilter] = useState<SessionsFilter>(DEFAULT_SESSIONS_FILTER);

  const [exportOutDir, setExportOutDir] = useState("");
  const [reportYear, setReportYear] = useState("");
  const [reportWeek, setReportWeek] = useState("");
  const [reportOutDir, setReportOutDir] = useState("");

  const [liveState, setLiveState] = useState<TimerState | null>(null);

  const { register, handleSubmit, watch, reset, setValue, formState } = useForm<TimerFormValues>({
    defaultValues: DEFAULT_TIMER_VALUES
  });

  const addToast = useCallback((level: ToastLevel, text: string) => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((prev) => [...prev, { id, level, text }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((item) => item.id !== id)), 2800);
  }, []);

  useEffect(() => {
    try {
      const timerRaw = localStorage.getItem(TIMER_FORM_STORAGE_KEY);
      if (timerRaw) reset(sanitizeTimerValues(JSON.parse(timerRaw) as Partial<TimerFormValues>));
      const filterRaw = localStorage.getItem(SESSIONS_FILTER_STORAGE_KEY);
      if (filterRaw) {
        const parsed = JSON.parse(filterRaw) as Partial<SessionsDraft>;
        const merged = {
          since: String(parsed.since ?? ""),
          tag: String(parsed.tag ?? ""),
          taskContains: String(parsed.taskContains ?? ""),
          limit: String(parsed.limit ?? "60")
        };
        setSessionsDraft(merged);
        const rawLimit = Number(merged.limit);
        setSessionsFilter({
          since: merged.since,
          tag: merged.tag,
          taskContains: merged.taskContains,
          limit: Number.isNaN(rawLimit) ? 60 : Math.max(1, Math.min(2000, Math.floor(rawLimit)))
        });
      }
      const outputRaw = localStorage.getItem(OUTPUT_FORM_STORAGE_KEY);
      if (outputRaw) {
        const parsed = JSON.parse(outputRaw) as Record<string, string>;
        setExportOutDir(String(parsed.exportOutDir ?? ""));
        setReportYear(String(parsed.reportYear ?? ""));
        setReportWeek(String(parsed.reportWeek ?? ""));
        setReportOutDir(String(parsed.reportOutDir ?? ""));
      }
    } catch {
      // Ignore local storage errors.
    }
  }, [reset]);

  useEffect(() => {
    const sub = watch((values) => {
      try {
        localStorage.setItem(TIMER_FORM_STORAGE_KEY, JSON.stringify(values));
      } catch {
        // Ignore local storage errors.
      }
    });
    return () => sub.unsubscribe();
  }, [watch]);

  useEffect(() => {
    try {
      localStorage.setItem(SESSIONS_FILTER_STORAGE_KEY, JSON.stringify(sessionsDraft));
    } catch {
      // Ignore local storage errors.
    }
  }, [sessionsDraft]);

  useEffect(() => {
    try {
      localStorage.setItem(
        OUTPUT_FORM_STORAGE_KEY,
        JSON.stringify({ exportOutDir, reportYear, reportWeek, reportOutDir })
      );
    } catch {
      // Ignore local storage errors.
    }
  }, [exportOutDir, reportOutDir, reportWeek, reportYear]);

  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: getMeta });
  const stateQuery = useQuery({ queryKey: ["timer-state"], queryFn: getTimerState, refetchInterval: 5000 });
  const statsQuery = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const sessionsQuery = useQuery({
    queryKey: ["sessions", sessionsFilter],
    queryFn: () => listSessions(sessionsFilter)
  });

  useEffect(() => {
    if (!stateQuery.data) return;
    setLiveState(stateQuery.data);
    const eventName = String(stateQuery.data.last_event?.event ?? "");
    if (eventName === "interval_start") {
      const duration = Number(stateQuery.data.last_event?.duration_sec ?? 0);
      if (duration > 0) setIntervalTotalSec(duration);
    } else if (eventName === "tick" && intervalTotalSec <= 0) {
      const remaining = Number(stateQuery.data.last_event?.remaining_sec ?? 0);
      if (remaining > 0) setIntervalTotalSec(remaining);
    }
    if (stateQuery.data.status !== "running" && stateQuery.data.status !== "stopping") {
      setIntervalTotalSec(0);
    }
  }, [intervalTotalSec, stateQuery.data]);

  const refetchCoreData = useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["timer-state"] }),
      queryClient.invalidateQueries({ queryKey: ["stats"] }),
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    ]);
  }, [queryClient]);

  useEffect(() => {
    let retryTimer: number | undefined;
    const connect = () => {
      if (typeof EventSource === "undefined") return;
      const source = new EventSource("/api/v1/timer/stream");
      streamRef.current = source;
      source.onmessage = (raw) => {
        try {
          const event = JSON.parse(raw.data) as TimerStreamEvent;
          const name = String(event.event ?? "");
          if (name === "tick") {
            const remaining = Number(event.remaining_sec ?? 0);
            const label = String(event.label ?? "");
            setIntervalTotalSec((prev) => (prev > 0 ? prev : Math.max(1, remaining)));
            setLiveState((prev) => ({
              status: "running",
              stage: label,
              remaining_sec: remaining,
              detail: prev?.detail || "计时进行中",
              completed_work_sessions: prev?.completed_work_sessions ?? 0,
              last_event: event
            }));
            return;
          }
          if (name === "interval_start") {
            const duration = Number(event.duration_sec ?? 0);
            setIntervalTotalSec(Math.max(0, duration));
            setLiveState((prev) => ({
              status: "running",
              stage: String(event.label ?? ""),
              remaining_sec: duration,
              detail: "计时进行中",
              completed_work_sessions: prev?.completed_work_sessions ?? 0,
              last_event: event
            }));
            return;
          }
          if (name === "interval_end") {
            setStatusLine(`${String(event.label ?? "")} ${Boolean(event.completed) ? "完成" : "中断"}`);
            void refetchCoreData();
            return;
          }
          if (name === "run_end") {
            setIntervalTotalSec(0);
            setLiveState({
              status: "idle",
              stage: "空闲",
              remaining_sec: 0,
              detail: Boolean(event.interrupted) ? "计时结束（中断）" : "计时完成",
              completed_work_sessions: Number(event.completed_work_sessions ?? 0),
              last_event: event
            });
            setStatusLine(Boolean(event.interrupted) ? "计时结束（中断）" : "计时完成");
            void refetchCoreData();
            return;
          }
          if (name === "runner_error") {
            const msg = String(event.message ?? "计时线程异常");
            setLiveState((prev) => ({
              status: "error",
              stage: prev?.stage || "异常",
              remaining_sec: prev?.remaining_sec ?? 0,
              detail: msg,
              completed_work_sessions: prev?.completed_work_sessions ?? 0,
              last_event: event
            }));
            setStatusLine(msg);
            addToast("error", msg);
          }
        } catch {
          // Ignore malformed events.
        }
      };
      source.onerror = () => {
        source.close();
        streamRef.current = null;
        retryTimer = window.setTimeout(connect, 1200);
      };
    };
    connect();
    return () => {
      if (retryTimer) window.clearTimeout(retryTimer);
      if (streamRef.current) {
        streamRef.current.close();
        streamRef.current = null;
      }
    };
  }, [addToast, refetchCoreData]);

  const currentState = liveState ?? stateQuery.data ?? null;
  const isRunning = currentState?.status === "running" || currentState?.status === "stopping";

  const startMutation = useMutation({
    mutationFn: startTimer,
    onSuccess: async (result) => {
      setLiveState(result);
      setStatusLine("计时已启动");
      addToast("success", "计时已启动");
      await refetchCoreData();
    },
    onError: (error: Error) => {
      setStatusLine(error.message);
      addToast("error", error.message);
    }
  });

  const stopMutation = useMutation({
    mutationFn: stopTimer,
    onSuccess: async (result) => {
      setLiveState(result);
      setStatusLine("已发送停止请求");
      addToast("info", "已发送停止请求");
      await queryClient.invalidateQueries({ queryKey: ["timer-state"] });
    },
    onError: (error: Error) => {
      setStatusLine(error.message);
      addToast("error", error.message);
    }
  });

  const exportMutation = useMutation({
    mutationFn: exportCsv,
    onSuccess: (result) => {
      const msg = `CSV 导出完成：${result.path}`;
      setStatusLine(msg);
      addToast("success", msg);
    },
    onError: (error: Error) => {
      setStatusLine(error.message);
      addToast("error", error.message);
    }
  });

  const reportMutation = useMutation({
    mutationFn: generateWeeklyReport,
    onSuccess: (result) => {
      const msg = `周报已生成：${result.path}`;
      setStatusLine(msg);
      addToast("success", msg);
    },
    onError: (error: Error) => {
      setStatusLine(error.message);
      addToast("error", error.message);
    }
  });

  const triggerStart = handleSubmit(async (values) => {
    await startMutation.mutateAsync({
      ...values,
      task: values.task.trim(),
      tags: values.tags.trim()
    });
  });

  const triggerStop = useCallback(() => {
    if (isRunning && !stopMutation.isPending) stopMutation.mutate();
  }, [isRunning, stopMutation]);

  const refreshAll = useCallback(async () => {
    await refetchCoreData();
    await queryClient.invalidateQueries({ queryKey: ["meta"] });
    setStatusLine("已刷新");
  }, [queryClient, refetchCoreData]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const meta = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (meta && key === "enter") {
        event.preventDefault();
        void triggerStart();
      } else if (meta && key === "r") {
        event.preventDefault();
        void refreshAll();
      } else if (meta && key === "l") {
        event.preventDefault();
        setActiveTab("sessions");
      } else if (key === "escape" && isRunning) {
        event.preventDefault();
        triggerStop();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isRunning, refreshAll, triggerStart, triggerStop]);

  const applySessionsFilter = () => {
    const parsedLimit = Number(sessionsDraft.limit);
    setSessionsFilter({
      since: sessionsDraft.since,
      tag: sessionsDraft.tag,
      taskContains: sessionsDraft.taskContains,
      limit: Number.isNaN(parsedLimit) ? 60 : Math.max(1, Math.min(2000, Math.floor(parsedLimit)))
    });
    setStatusLine("已应用日志筛选");
  };

  const resetSessionsFilter = () => {
    setSessionsDraft(DEFAULT_SESSIONS_DRAFT);
    setSessionsFilter(DEFAULT_SESSIONS_FILTER);
    setStatusLine("已重置日志筛选");
  };

  const applyPreset = (preset: TimerPreset) => {
    setValue("work_minutes", preset.work, { shouldDirty: true });
    setValue("break_minutes", preset.break, { shouldDirty: true });
    setValue("long_break_minutes", preset.longBreak, { shouldDirty: true });
    setValue("cycles", preset.cycles, { shouldDirty: true });
  };

  const busy = formState.isSubmitting || startMutation.isPending || stopMutation.isPending;
  const stats = statsQuery.data ?? DEFAULT_STATS;
  const sessions = sessionsQuery.data ?? [];
  const metaLine = metaQuery.data ? `v${metaQuery.data.version} · ${metaQuery.data.platform}` : "";
  const progressPercent =
    isRunning && intervalTotalSec > 0
      ? Math.min(100, Math.max(0, ((intervalTotalSec - Math.max(0, currentState?.remaining_sec ?? 0)) / intervalTotalSec) * 100))
      : 0;

  return (
    <div className="app-shell">
      <header className="px-5 py-4">
        <div className="panel panel-body flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="m-0 text-[26px] font-semibold">FocusLog</h1>
            <p className="m-0 text-sm muted">番茄钟与专注日志（WebView 版）</p>
          </div>
          <ActionRow>
            <button className="btn btn-ghost" type="button" onClick={() => void refreshAll()}>
              刷新
            </button>
            <span className={statusClass(currentState?.status ?? "idle")}>{statusText(currentState?.status ?? "idle")}</span>
          </ActionRow>
        </div>
      </header>

      <main className="app-main">
        <div className="workspace-grid workspace-grid-single">
          <section className="panel min-h-0 flex flex-col overflow-hidden">
            <div className="panel-body flex min-h-0 flex-1 flex-col gap-4 overflow-auto">
              <div className="tabs">
                <TabButton active={activeTab === "settings"} text="计时设置" onClick={() => setActiveTab("settings")} />
                <TabButton active={activeTab === "timer"} text="计时看板" onClick={() => setActiveTab("timer")} />
                <TabButton active={activeTab === "stats"} text="统计与产出" onClick={() => setActiveTab("stats")} />
                <TabButton active={activeTab === "sessions"} text="日志" onClick={() => setActiveTab("sessions")} />
              </div>

              {activeTab === "settings" ? (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between">
                    <strong className="text-[15px]">计时设置</strong>
                    <span className="text-xs muted">Ctrl/Cmd+Enter 开始 · Esc 停止</span>
                  </div>
                  <div className="preset-grid">
                    {TIMER_PRESETS.map((preset) => (
                      <button key={preset.label} className="preset-chip" type="button" onClick={() => applyPreset(preset)}>
                        {preset.label}
                      </button>
                    ))}
                  </div>
                  <form className="flex flex-col gap-3" onSubmit={(e) => void triggerStart(e)}>
                    <label className="text-sm">
                      <div className="mb-1 font-medium">任务</div>
                      <input className="field" placeholder="例如：论文阅读" {...register("task")} />
                    </label>
                    <label className="text-sm">
                      <div className="mb-1 font-medium">标签（逗号分隔）</div>
                      <input className="field" placeholder="学习,深度工作" {...register("tags")} />
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <label className="text-sm">
                        <div className="mb-1 font-medium">工作(分钟)</div>
                        <input className="field" type="number" min={0} step="0.5" {...register("work_minutes", { valueAsNumber: true })} />
                      </label>
                      <label className="text-sm">
                        <div className="mb-1 font-medium">短休息(分钟)</div>
                        <input className="field" type="number" min={0} step="0.5" {...register("break_minutes", { valueAsNumber: true })} />
                      </label>
                      <label className="text-sm">
                        <div className="mb-1 font-medium">长休息(分钟)</div>
                        <input className="field" type="number" min={0} step="0.5" {...register("long_break_minutes", { valueAsNumber: true })} />
                      </label>
                      <label className="text-sm">
                        <div className="mb-1 font-medium">循环次数</div>
                        <input className="field" type="number" min={1} step="1" {...register("cycles", { valueAsNumber: true })} />
                      </label>
                    </div>
                    <label className="text-sm">
                      <div className="mb-1 font-medium">刷新间隔(秒)</div>
                      <input className="field" type="number" min={0} step="0.1" {...register("tick_seconds", { valueAsNumber: true })} />
                    </label>
                    <label className="flex items-center gap-2 text-sm muted">
                      <input type="checkbox" {...register("notify")} />
                      桌面通知
                    </label>
                    <label className="flex items-center gap-2 text-sm muted">
                      <input type="checkbox" {...register("sound")} />
                      启用提示音
                    </label>
                    <ActionRow>
                      <button className="btn btn-primary" type="submit" disabled={busy || isRunning}>
                        开始
                      </button>
                      <button className="btn btn-danger" type="button" onClick={triggerStop} disabled={busy || !isRunning}>
                        停止
                      </button>
                    </ActionRow>
                  </form>
                  <div className="rounded-[10px] border border-[#dce5f0] bg-[#f8fbff] p-3 text-xs muted">
                    <div>数据库：{metaQuery.data?.db_path ?? "-"}</div>
                    <div>{metaLine}</div>
                    <div className="mt-1">最后事件：{summarizeLastEvent(currentState)}</div>
                  </div>
                </div>
              ) : null}

              {activeTab === "timer" ? (
                <div className="flex flex-col gap-4">
                  <div className="rounded-[10px] border border-[#dce5f0] bg-[#f8fbff] p-3">
                    <div className="mb-2 flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm muted">当前阶段</div>
                        <div className="text-[20px] font-semibold">{currentState?.stage || "等待开始"}</div>
                      </div>
                      <div className="text-right">
                        <div className="countdown">{formatCountdown(currentState?.remaining_sec ?? 0)}</div>
                        <div className="text-sm muted">{currentState?.detail || ""}</div>
                      </div>
                    </div>
                    <div className="progress-track">
                      <div className="progress-bar" style={{ width: `${progressPercent.toFixed(2)}%` }} />
                    </div>
                  </div>
                  <div className="info-grid">
                    <div className="stat-card">
                      <div className="stat-title">本轮完成工作会话</div>
                      <div className="text-[26px] font-semibold">{currentState?.completed_work_sessions ?? 0}</div>
                    </div>
                    <div className="stat-card">
                      <div className="stat-title">当前状态</div>
                      <div className="text-[18px] font-semibold">{statusText(currentState?.status ?? "idle")}</div>
                      <div className="text-sm muted">{currentState?.detail || "-"}</div>
                    </div>
                  </div>
                </div>
              ) : null}

              {activeTab === "stats" ? (
                <div className="flex flex-col gap-4">
                  <div className="stats-grid">
                    <StatCard title="今天" stats={stats.today} />
                    <StatCard title="本周" stats={stats.this_week} />
                    <StatCard title="最近 7 天" stats={stats.last_7_days} />
                  </div>
                  <div className="rounded-[10px] border border-[#dce5f0] bg-white p-3">
                    <strong className="text-[15px]">产出</strong>
                    <div className="mt-2 text-sm muted">导出目录（可选）</div>
                    <input className="field mt-2" value={exportOutDir} onChange={(e) => setExportOutDir(e.target.value)} placeholder="例如：focuslog/out" />
                    <div className="mt-3">
                      <button className="btn btn-ghost" type="button" onClick={() => exportMutation.mutate(exportOutDir.trim() || undefined)} disabled={exportMutation.isPending}>
                        导出 CSV
                      </button>
                    </div>
                    <div className="mt-4 text-sm muted">周报参数（可选）</div>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                      <input className="field" placeholder="year" value={reportYear} onChange={(e) => setReportYear(e.target.value)} />
                      <input className="field" placeholder="week" value={reportWeek} onChange={(e) => setReportWeek(e.target.value)} />
                      <input className="field" placeholder="out_dir" value={reportOutDir} onChange={(e) => setReportOutDir(e.target.value)} />
                    </div>
                    <div className="mt-3">
                      <button
                        className="btn btn-primary"
                        type="button"
                        onClick={() => reportMutation.mutate({ year: parseNumberOrNull(reportYear), week: parseNumberOrNull(reportWeek), outDir: reportOutDir })}
                        disabled={reportMutation.isPending}
                      >
                        生成周报
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}

              {activeTab === "sessions" ? (
                <div className="rounded-[10px] border border-[#dce5f0] bg-white p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <strong className="text-[15px]">日志筛选</strong>
                    <span className="text-xs muted">共 {sessions.length} 条</span>
                  </div>
                  <div className="grid grid-cols-1 gap-2 md:grid-cols-4">
                    <input className="field" placeholder="since: YYYY-MM-DD 或 ISO" value={sessionsDraft.since} onChange={(e) => setSessionsDraft((prev) => ({ ...prev, since: e.target.value }))} />
                    <input className="field" placeholder="标签" value={sessionsDraft.tag} onChange={(e) => setSessionsDraft((prev) => ({ ...prev, tag: e.target.value }))} />
                    <input className="field" placeholder="任务关键字" value={sessionsDraft.taskContains} onChange={(e) => setSessionsDraft((prev) => ({ ...prev, taskContains: e.target.value }))} />
                    <input className="field" placeholder="limit" value={sessionsDraft.limit} onChange={(e) => setSessionsDraft((prev) => ({ ...prev, limit: e.target.value }))} />
                  </div>
                  <div className="mt-2 flex gap-2">
                    <button className="btn btn-ghost" type="button" onClick={applySessionsFilter}>应用筛选</button>
                    <button className="btn btn-ghost" type="button" onClick={() => void sessionsQuery.refetch()}>刷新日志</button>
                    <button className="btn btn-ghost" type="button" onClick={resetSessionsFilter}>重置</button>
                  </div>
                  <div className="table-wrap mt-3 max-h-[420px]">
                    <table className="table">
                      <thead>
                        <tr>
                          <th>开始时间</th>
                          <th>类型</th>
                          <th>时长</th>
                          <th>状态</th>
                          <th>任务</th>
                          <th>标签</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sessions.length === 0 ? (
                          <tr><td colSpan={6} className="muted">暂无记录</td></tr>
                        ) : (
                          sessions.map((item) => (
                            <tr key={item.id}>
                              <td>{formatDateTime(item.start_time)}</td>
                              <td>{item.kind === "work" ? "工作" : "休息"}</td>
                              <td>{formatDuration(item.duration_sec)}</td>
                              <td>{item.completed ? "完成" : `中断(${item.interrupted_reason || "未知"})`}</td>
                              <td>{item.task || "-"}</td>
                              <td>{item.tags || "-"}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </main>

      <footer className="px-5 pb-4">
        <div className="panel panel-body flex items-center justify-between gap-2 text-sm">
          <span className="muted">{statusLine}</span>
          <span className="muted">Ctrl/Cmd+R 刷新 · Ctrl/Cmd+L 日志页</span>
        </div>
      </footer>

      <div className="toast-stack">
        {toasts.map((item) => (
          <div key={item.id} className={`toast ${item.level === "success" ? "toast-success" : item.level === "error" ? "toast-error" : "toast-info"}`}>
            {item.text}
          </div>
        ))}
      </div>
    </div>
  );
}
