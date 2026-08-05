import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const WEB_URL = "http://127.0.0.1:8001";
const outputDir = join(process.cwd(), "output", "playwright", "b5-interaction-fixes");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
page.on("dialog", (dialog) => dialog.accept());

try {
  await page.goto(`${WEB_URL}/practice`);
  const card = page.locator(".test-card").filter({ hasText: "剑雅5 Test B" });
  await card.getByRole("button", { name: "Part 1", exact: true }).click();
  await page.locator(".exam-workbench").waitFor();
  await page.locator('[data-source-answer-id="121099"]').scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(outputDir, "b5-test-b-part1-q8-14.png") });
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.locator(".test-card").first().waitFor();

  await card.getByRole("button", { name: "Part 3", exact: true }).click();
  await page.locator(".exam-workbench").waitFor();
  const matrix = page.locator(".source-matching-matrix").first();
  await matrix.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(outputDir, "b5-test-b-part3-q28-33-workbench.png") });
  await matrix.screenshot({ path: join(outputDir, "b5-test-b-part3-q28-33-matrix.png") });
} finally {
  await browser.close();
}

console.log(JSON.stringify({ outputDir }, null, 2));
