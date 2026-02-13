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
        if (url.includes("/api/prompts")) {
          return {
            ok: true,
            json: async () => ({ items: [], total: 0 })
          } as Response;
        }
        return {
          ok: true,
          json: async () => ({ status: "ok" })
        } as Response;
      })
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders application title", () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    );
    expect(screen.getByText("Prompt Vault")).toBeInTheDocument();
  });
});
