import { chromium } from "@playwright/test";

const WEB_URL = "http://127.0.0.1:8001";

const cases = [
  { type: 0, title: "剑雅5 Test B", part: 1, control: "input:not([type='hidden'])", value: "sample answer" },
  { type: 1, title: "剑雅6 Test A", part: 2, control: "input[type='radio']" },
  { type: 2, title: "剑雅7 Test A", part: 3, control: "input[type='checkbox']" },
  { type: 3, title: "剑雅5 Test A", part: 1, control: "input[type='radio']" },
  { type: 4, title: "剑雅5 Test B", part: 3, control: ".source-matching-matrix input[type='radio']" }
];

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.on("dialog", (dialog) => dialog.accept());
const results = [];

try {
  await page.goto(`${WEB_URL}/practice`);
  await page.locator(".test-card").first().waitFor();

  for (const item of cases) {
    const card = page.locator(".test-card").filter({ hasText: item.title });
    await card.getByRole("button", { name: `Part ${item.part}`, exact: true }).click();
    await page.locator(".exam-workbench").waitFor();

    const block = page.locator(`.source-question-block[data-source-question-type="${item.type}"]`).first();
    await block.waitFor();
    const control = block.locator(item.control).first();
    await control.scrollIntoViewIfNeeded();

    if (item.type === 0) {
      await control.click();
      const focusedControl = block.locator(item.control).first();
      await focusedControl.pressSequentially(item.value, { delay: 5 });
      await page.waitForTimeout(100);
      const actualValue = await focusedControl.inputValue();
      if (actualValue !== item.value) {
        const answerId = await focusedControl.getAttribute("data-source-answer-id");
        const progress = await page.locator(".exam-progress").innerText();
        throw new Error(`completion value was not retained: id=${answerId} actual=${JSON.stringify(actualValue)} progress=${JSON.stringify(progress)}`);
      }
    } else {
      await control.check();
      if (!await control.isChecked()) throw new Error(`question type ${item.type} did not stay checked`);
    }

    results.push({ type: item.type, title: item.title, part: item.part, passed: true });
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await page.locator(".test-card").first().waitFor();
  }

  const c5b = page.locator(".test-card").filter({ hasText: "剑雅5 Test B" });
  await c5b.getByRole("button", { name: "Part 1", exact: true }).click();
  await page.locator(".exam-workbench").waitFor();
  const q10 = page.locator('[data-source-answer-id="121101"]');
  await q10.fill("E C");
  if (await q10.inputValue() !== "E C") throw new Error("question 10 did not retain two answers");
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.locator(".test-card").first().waitFor();

  await c5b.getByRole("button", { name: "Part 3", exact: true }).click();
  await page.locator(".exam-workbench").waitFor();
  const matrix = page.locator('.source-question-block[data-source-interaction-mode="matching_matrix"] .source-matching-matrix').first();
  if (await matrix.locator("tbody tr").count() !== 6) throw new Error("glow-worm matrix does not have six question rows");
  if (await matrix.locator("thead th").count() !== 6) throw new Error("glow-worm matrix does not have A-E columns");
  const firstRow = matrix.locator("tbody tr").first();
  await firstRow.locator("input[type='radio']").nth(0).check();
  await firstRow.locator("input[type='radio']").nth(3).check();
  if (await firstRow.locator("input[type='radio']:checked").count() !== 1) throw new Error("matching row allowed more than one answer");
  if (!await firstRow.locator("input[type='radio']").nth(3).isChecked()) throw new Error("matching row did not retain the replacement answer");
  if (await matrix.locator("select").count()) throw new Error("matching matrix still contains the obsolete select control");
  results.push({ type: 4, title: "剑雅5 Test B", part: 3, passed: true, detail: "6xA-E matrix" });
  await page.getByRole("button", { name: "退出", exact: true }).click();
  await page.locator(".test-card").first().waitFor();
} finally {
  await browser.close();
}

console.log(JSON.stringify({ passed: results.length, results }, null, 2));
