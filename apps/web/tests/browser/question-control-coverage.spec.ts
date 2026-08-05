import { expect, test } from "@playwright/test";
import { assertPartLayout } from "./full-question-bank-assertions";

type Question = { id: string; number?: number };
type Group = { shared_response?: boolean; questions: Question[] };
type Part = { number: number; groups: Group[] };
type PublicTest = { id: string; title: string; parts: Part[] };

const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8010";

test.describe.configure({ timeout: 10 * 60 * 1000 });

function expectedControlIds(part: Part): string[] {
  return part.groups.flatMap((group) => {
    if (group.shared_response) {
      const first = group.questions[0];
      return first ? [String(first.id)] : [];
    }
    return group.questions.map((question) => String(question.id));
  });
}

test("all 58 tests expose every answer control across all 174 Parts", async ({ page, request }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const indexResponse = await request.get(`${API_BASE_URL}/api/v1/question-bank/tests`);
  expect(indexResponse.ok()).toBeTruthy();
  const index = await indexResponse.json() as { items: Array<{ id: string; title: string }> };
  expect(index.items).toHaveLength(58);

  const payloads: PublicTest[] = [];
  for (const item of index.items) {
    const response = await request.get(
      `${API_BASE_URL}/api/v1/question-bank/tests/${encodeURIComponent(item.id)}`
    );
    expect(response.ok(), item.id).toBeTruthy();
    payloads.push(await response.json() as PublicTest);
  }

  await page.goto("/practice");
  await expect(page.locator(".test-card")).toHaveCount(58);

  let visitedParts = 0;
  for (const payload of payloads) {
    const card = page.locator(".test-card").filter({ hasText: payload.title });
    await expect(card, payload.title).toHaveCount(1);
    await card.getByRole("button", { name: "整套学习", exact: true }).click();
    await expect(page.locator(".exam-workbench")).toBeVisible();

    for (const part of payload.parts) {
      const partTab = page.locator(".dock-section").nth(part.number - 1).locator(".dock-section-label");
      await partTab.click();
      await expect(partTab).toHaveAttribute("aria-selected", "true");

      const expectedIds = expectedControlIds(part).sort();
      const actualIds = await page.locator('[id^="question-"]').evaluateAll((elements) =>
        [...new Set(elements.map((element) => element.id.slice("question-".length)).filter(Boolean))].sort()
      );
      expect(actualIds, `${payload.title} Part ${part.number} answer controls`).toEqual(expectedIds);

      await assertPartLayout(page, payload.title, part.number);

      const sourceMatrixRows = await page.locator(".source-matching-matrix tbody tr").evaluateAll((rows) =>
        rows.map((row) => row.id.slice("question-".length)).filter(Boolean)
      );
      expect(
        new Set(sourceMatrixRows).size,
        `${payload.title} Part ${part.number} source matrix row ids`
      ).toBe(sourceMatrixRows.length);
      visitedParts += 1;
    }

    await page.getByRole("button", { name: "退出", exact: true }).click();
    await expect(page.locator(".test-card")).toHaveCount(58);
  }

  expect(visitedParts).toBe(174);
  expect(pageErrors).toEqual([]);
});

test("剑雅6 Test A 显示15–21，并让23与24分别作答", async ({ page, request }) => {
  const response = await request.get(`${API_BASE_URL}/api/v1/question-bank/tests/b6-test-a`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json() as PublicTest;
  const questions = payload.parts.flatMap((part) => part.groups.flatMap((group) => group.questions));
  const question23 = questions.find((question) => question.number === 23);
  const question24 = questions.find((question) => question.number === 24);
  expect(question23).toBeTruthy();
  expect(question24).toBeTruthy();

  await page.goto("/practice");
  const card = page.locator(".test-card").filter({ hasText: payload.title });
  await card.getByRole("button", { name: "整套学习", exact: true }).click();
  await expect(page.locator(".exam-workbench")).toBeVisible();

  const part2Tab = page.locator(".dock-section").nth(1).locator(".dock-section-label");
  await part2Tab.click();
  await expect(part2Tab).toHaveAttribute("aria-selected", "true");

  const matrixNumbers = await page.locator(".source-matching-matrix .source-matrix-question-number").allTextContents();
  expect(matrixNumbers.map((text) => Number(text.trim()))).toEqual([15, 16, 17, 18, 19, 20, 21]);

  const row23 = page.locator(`#question-${question23!.id}`);
  const row24 = page.locator(`#question-${question24!.id}`);
  await expect(row23.locator('input[type="radio"]')).toHaveCount(4);
  await expect(row24.locator('input[type="radio"]')).toHaveCount(4);
  await row23.locator("label").nth(1).click();
  await row24.locator("label").nth(0).click();

  await expect(row23.locator('input[type="radio"]').nth(1)).toBeChecked();
  await expect(row24.locator('input[type="radio"]').nth(0)).toBeChecked();
  await expect(row23.locator('input[type="radio"]').nth(0)).not.toBeChecked();
  await expect(row24.locator('input[type="radio"]').nth(1)).not.toBeChecked();
});

test("剑雅6 Test B 显示Section A示例且不把示例算作答题控件", async ({ page, request }) => {
  const response = await request.get(`${API_BASE_URL}/api/v1/question-bank/tests/b6-test-b`);
  expect(response.ok()).toBeTruthy();
  const payload = await response.json() as PublicTest;

  await page.goto("/practice");
  const card = page.locator(".test-card").filter({ hasText: payload.title });
  await card.getByRole("button", { name: "整套学习", exact: true }).click();
  await expect(page.locator(".exam-workbench")).toBeVisible();

  const part2Tab = page.locator(".dock-section").nth(1).locator(".dock-section-label");
  await part2Tab.click();
  await expect(part2Tab).toHaveAttribute("aria-selected", "true");

  const example = page.getByRole("group", { name: "示例答案" });
  await expect(example).toHaveCount(1);
  await expect(example).toContainText("Example:");
  await expect(example).toContainText("Answer");
  await expect(example).toContainText("Section A");
  await expect(example).toContainText("iii");

  const matrix = example.locator("xpath=ancestor::*[contains(@class, 'source-question-block')][1]")
    .locator(".source-matching-matrix");
  const matrixNumbers = await matrix.locator(".source-matrix-question-number").allTextContents();
  expect(matrixNumbers.map((text) => Number(text.trim()))).toEqual([15, 16, 17, 18, 19, 20, 21]);
  await expect(matrix.locator('input[type="radio"]')).toHaveCount(7 * 12);
  await expect(example.locator("input, button, select, textarea")).toHaveCount(0);
});
