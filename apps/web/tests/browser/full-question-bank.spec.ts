import { expect, test } from "@playwright/test";

type Question = { id: string };
type Group = {
  shared_response?: boolean;
  questions: Question[];
};
type Part = {
  number: number;
  groups: Group[];
};
type PublicTest = {
  id: string;
  title: string;
  parts: Part[];
};

const API_BASE_URL = "http://127.0.0.1:8010";

function expectedControlIds(part: Part): string[] {
  return part.groups.flatMap((group) => {
    if (group.shared_response) {
      const first = group.questions[0];
      return first ? [String(first.id)] : [];
    }
    return group.questions.map((question) => String(question.id));
  });
}

test("all 58 tests and 174 Parts render every answer control without desktop overflow", async ({
  page,
  request
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const indexResponse = await request.get(`${API_BASE_URL}/api/v1/question-bank/tests`);
  expect(indexResponse.ok()).toBeTruthy();
  const index = await indexResponse.json() as { items: Array<{ id: string; title: string }> };
  expect(index.items).toHaveLength(58);

  const tests = new Map<string, PublicTest>();
  for (const item of index.items) {
    const response = await request.get(
      `${API_BASE_URL}/api/v1/question-bank/tests/${encodeURIComponent(item.id)}`
    );
    expect(response.ok(), item.id).toBeTruthy();
    const testPayload = await response.json() as PublicTest;
    tests.set(testPayload.title, testPayload);
  }

  await page.goto("/practice");
  await expect(page.locator(".test-card")).toHaveCount(58);

  let visitedParts = 0;
  for (let cardIndex = 0; cardIndex < 58; cardIndex += 1) {
    const initialCard = page.locator(".test-card").nth(cardIndex);
    const cardLines = (await initialCard.innerText()).split("\n").map((line) => line.trim());
    const title = cardLines[1];
    const testPayload = tests.get(title);
    expect(testPayload, `UI title must map to API test: ${title}`).toBeTruthy();

    for (let partNumber = 1; partNumber <= 3; partNumber += 1) {
      const card = page.locator(".test-card").nth(cardIndex);
      await card.getByRole("button", { name: `Part ${partNumber}`, exact: true }).click();
      await expect(page.getByRole("button", { name: "退出", exact: true })).toBeVisible();

      const part = testPayload?.parts.find((item) => item.number === partNumber);
      expect(part, `${title} Part ${partNumber}`).toBeTruthy();
      const expectedIds = expectedControlIds(part as Part).sort();
      const actualIds = await page.locator('[id^="question-"]').evaluateAll((elements) =>
        [...new Set(elements.map((element) => element.id.slice("question-".length)).filter(Boolean))].sort()
      );
      expect(actualIds, `${title} Part ${partNumber} answer controls`).toEqual(expectedIds);

      const layout = await page.evaluate(() => {
        const overflowing = [
          ...document.querySelectorAll<HTMLElement>(
            ".questions-scroll,.matching-text-group,.matching-matrix-group,.matching-interactive-bank"
          )
        ]
          .filter((element) => element.scrollWidth > element.clientWidth + 2)
          .map((element) => ({
            className: element.className,
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth
          }));
        return {
          documentOverflow:
            document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
          overflowing,
          unresolvedTemplateFallbacks: [
            ...document.querySelectorAll<HTMLElement>(".structured-completion")
          ].filter((element) => element.innerText.includes("_____")).length
        };
      });
      expect(layout.documentOverflow, `${title} Part ${partNumber} document overflow`).toBe(false);
      expect(layout.overflowing, `${title} Part ${partNumber} component overflow`).toEqual([]);
      expect(
        layout.unresolvedTemplateFallbacks,
        `${title} Part ${partNumber} unresolved template placeholders`
      ).toBe(0);

      visitedParts += 1;
      await page.getByRole("button", { name: "退出", exact: true }).click();
      await expect(page.locator(".test-card")).toHaveCount(58);
    }
  }

  expect(visitedParts).toBe(174);
  expect(pageErrors).toEqual([]);
});
