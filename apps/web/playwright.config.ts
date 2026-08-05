import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
import { join, resolve } from "node:path";

const workspaceRoot = resolve(process.cwd(), "../..");
const apiBaseUrl = process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:18010";
const webBaseUrl = process.env.PLAYWRIGHT_WEB_BASE_URL || "http://127.0.0.1:18001";
const apiPort = new URL(apiBaseUrl).port || "80";
const webPort = new URL(webBaseUrl).port || "80";
const e2eDatabasePath = process.env.PLAYWRIGHT_SESSION_DB_PATH
  || join(workspaceRoot, "tmp", `playwright-e2e-${process.pid}.sqlite3`);
const reuseExistingServer = process.env.PLAYWRIGHT_REUSE_SERVERS === "1";
process.env.PLAYWRIGHT_API_BASE_URL ||= apiBaseUrl;
process.env.NEXT_PUBLIC_API_BASE_URL = apiBaseUrl;
const chromeCandidates = [
  process.env.PLAYWRIGHT_BROWSER_EXECUTABLE_PATH,
  process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, "Google", "Chrome", "Bin", "chrome.exe") : "",
  process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe") : "",
  process.env.PROGRAMFILES ? join(process.env.PROGRAMFILES, "Google", "Chrome", "Application", "chrome.exe") : ""
];
const browserExecutablePath = chromeCandidates
  .find((candidate): candidate is string => Boolean(candidate && existsSync(candidate)));

export default defineConfig({
  testDir: "./tests/browser",
  timeout: 10 * 60 * 1000,
  expect: { timeout: 5_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  use: {
    baseURL: webBaseUrl,
    browserName: "chromium",
    ...(browserExecutablePath
      ? { launchOptions: { executablePath: browserExecutablePath } }
      : { channel: "msedge" }),
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  webServer: [
    {
      command: `python -m app.db_migrate && python -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: join(workspaceRoot, "services", "api"),
      url: `${apiBaseUrl}/api/v1/health`,
      env: {
        ...process.env,
        SESSION_DB_PATH: e2eDatabasePath,
        WEB_ORIGINS: webBaseUrl,
        AI_API_KEY: "",
        DASHSCOPE_API_KEY: "",
        DEEPSEEK_API_KEY: "",
        OPENAI_API_KEY: ""
      },
      reuseExistingServer,
      timeout: 120_000
    },
    {
      command: `pnpm exec next build && pnpm exec next start -H 127.0.0.1 -p ${webPort}`,
      cwd: join(workspaceRoot, "apps", "web"),
      url: `${webBaseUrl}/practice`,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE_URL: apiBaseUrl
      },
      reuseExistingServer,
      timeout: 120_000
    }
  ]
});
