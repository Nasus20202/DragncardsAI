import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.DASHBOARD_SMOKE_BASE_URL ?? "http://127.0.0.1:3001";

export default defineConfig({
  testDir: "./tests",
  timeout: 360_000,
  expect: {
    timeout: 15_000,
  },
  retries: process.env.CI ? 3 : 1,
  use: {
    baseURL,
    trace: "retain-on-failure",
    headless: true,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
      },
    },
  ],
});
