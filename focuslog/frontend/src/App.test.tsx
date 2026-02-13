import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import App from "./App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/v1/meta")) {
          return {
            ok: true,
            json: async () => ({ app: "FocusLog", version: "0.1.0", db_path: "db", platform: "test" })
          } as Response;
        }
        if (url.includes("/api/v1/stats")) {
          return {
            ok: true,
            json: async () => ({
              today: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 },
              this_week: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 },
              last_7_days: { work_sec: 0, break_sec: 0, work_sessions: 0, completed_work_sessions: 0, interrupted_sessions: 0 }
            })
          } as Response;
        }
        if (url.includes("/api/v1/timer/state")) {
          return {
            ok: true,
            json: async () => ({
              status: "idle",
              stage: "等待开始",
              remaining_sec: 0,
              detail: "",
              completed_work_sessions: 0,
              last_event: {}
            })
          } as Response;
        }
        if (url.includes("/api/v1/sessions")) {
          return {
            ok: true,
            json: async () => []
          } as Response;
        }
        return {
          ok: true,
          json: async () => ({ status: "ok" })
        } as Response;
      })
    );

    class MockEventSource {
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: (() => void) | null = null;
      close(): void {
        return;
      }
    }
    vi.stubGlobal("EventSource", MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders app title", async () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    );
    expect(await screen.findByText("FocusLog")).toBeInTheDocument();
  });
});
