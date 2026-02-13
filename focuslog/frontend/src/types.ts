export type TimerState = {
  status: string;
  stage: string;
  remaining_sec: number;
  detail: string;
  completed_work_sessions: number;
  last_event: Record<string, unknown>;
};

export type TimerStartRequest = {
  task: string;
  tags: string;
  work_minutes: number;
  break_minutes: number;
  long_break_minutes: number;
  cycles: number;
  tick_seconds: number;
  sound: boolean;
  notify: boolean;
};

export type SessionItem = {
  id: number;
  start_time: string;
  end_time: string;
  duration_sec: number;
  task: string;
  tags: string;
  kind: "work" | "break";
  completed: boolean;
  interrupted_reason: string | null;
};

export type StatsWindow = {
  work_sec: number;
  break_sec: number;
  work_sessions: number;
  completed_work_sessions: number;
  interrupted_sessions: number;
};

export type StatsResponse = {
  today: StatsWindow;
  this_week: StatsWindow;
  last_7_days: StatsWindow;
};

export type FileResult = {
  path: string;
};

export type MetaResponse = {
  app: string;
  version: string;
  db_path: string;
  platform: string;
};

export type TimerStreamEvent = {
  event: string;
  [key: string]: unknown;
};
