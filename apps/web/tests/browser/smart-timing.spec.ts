import { expect, test } from "@playwright/test";

test("答题页静止不计时，发生真实操作后才开始累计", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto("/practice");
  const card = page.locator(".test-card").first();
  await expect(card).toBeVisible();
  await card.locator(".secondary-button").click();
  await expect(page.locator(".exam-workbench")).toBeVisible();

  await page.waitForTimeout(2_200);
  const timer = page.locator(".exam-timer");
  await expect(timer.locator(".study-timer-status")).toHaveClass(/idle/);
  await expect(timer.locator("strong")).toHaveText("00:00");

  await page.mouse.move(700, 500);
  await expect(timer.locator(".study-timer-status")).toHaveClass(/active/, { timeout: 2_500 });
  await expect.poll(async () => timer.locator("strong").innerText(), { timeout: 3_500 })
    .not.toBe("00:00");
  expect(pageErrors).toEqual([]);
});

test("能力训练使用相同的智能计时规则", async ({ page }) => {
  await page.goto("/ability");
  const card = page.locator(".ability-skill-card").first();
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "开始8题训练" }).click();
  await expect(page.locator(".ability-session-meta")).toBeVisible();

  await page.waitForTimeout(2_200);
  const meta = page.locator(".ability-session-meta");
  await expect(meta.locator(".study-timer-state")).toHaveClass(/idle/);
  await expect(meta.locator("strong").nth(1)).toHaveText("00:00");

  await page.mouse.move(700, 500);
  await expect(meta.locator(".study-timer-state")).toHaveClass(/active/, { timeout: 2_500 });
  await expect.poll(async () => meta.locator("strong").nth(1).innerText(), { timeout: 3_500 })
    .not.toBe("00:00");
});
