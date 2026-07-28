import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["features/**/__tests__/**/*.test.{ts,tsx}"],
    // Clears the dashboard's configuration env vars before each test so the
    // suite does not inherit a developer's exported stack configuration.
    setupFiles: ["./vitest.setup.ts"],
  },
});
