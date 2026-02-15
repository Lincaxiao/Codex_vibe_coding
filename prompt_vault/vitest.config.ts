import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/**/*.test.ts", "tests/integration/**/*.test.ts"],
    reporters: ["default"],
    clearMocks: true,
    coverage: {
      enabled: false,
      provider: "v8",
      reporter: ["text", "lcov"],
      thresholds: {
        lines: 60,
        functions: 60,
        branches: 50,
        statements: 60,
      },
    },
  },
});
