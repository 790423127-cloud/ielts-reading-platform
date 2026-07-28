import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/browser",
  timeout: 5 * 60 * 1000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:8001",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command: "python -m uvicorn app.main:app --app-dir ../../services/api --host 127.0.0.1 --port 8010",
      url: "http://127.0.0.1:8010/api/v1/health",
      reuseExistingServer: true,
      timeout: 120_000
    },
    {
      command: "pnpm dev",
      url: "http://127.0.0.1:8001/practice",
      reuseExistingServer: true,
      timeout: 120_000
    }
  ]
});
