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
        const passageCopy = document.querySelector<HTMLElement>(".passage-copy");
        const questionsPane = document.querySelector<HTMLElement>(".questions-pane");
        const divider = document.querySelector<HTMLElement>(".exam-divider");
        const dock = document.querySelector<HTMLElement>(".exam-question-dock");
        const passageStyle = passageCopy ? getComputedStyle(passageCopy) : null;
        const questionStyle = questionsPane ? getComputedStyle(questionsPane) : null;
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
        const matrixSignatures = [
          ...document.querySelectorAll<HTMLTableElement>(".matching-answer-matrix")
        ].map((table) => ({
          headerCells: table.tHead?.rows[0]?.cells.length || 0,
          radioCells: table.tBodies[0]?.rows[0]?.querySelectorAll('input[type="radio"]').length || 0,
          rowHeight: Math.round(table.tBodies[0]?.rows[0]?.getBoundingClientRect().height || 0)
        }));
        const descriptiveMatching = [
          ...document.querySelectorAll<HTMLElement>(".matching-text-group")
        ].map((group) => {
          const list = group.querySelector<HTMLElement>(".matching-question-list");
          const bank = group.querySelector<HTMLElement>(".matching-interactive-bank");
          return {
            columns: getComputedStyle(group).gridTemplateColumns.split(" ").filter(Boolean).length,
            questionWidth: Math.round(list?.getBoundingClientRect().width || 0),
            bankWidth: Math.round(bank?.getBoundingClientRect().width || 0)
          };
        });
        const sectionLetters = [
          ...document.querySelectorAll<HTMLElement>(".passage-section-letter")
        ].map((element) => {
          const style = getComputedStyle(element);
          return {
            background: style.backgroundColor,
            borderWidth: style.borderTopWidth,
            fontWeight: style.fontWeight
          };
        });
        const sourceTableFontSizes = [
          ...document.querySelectorAll<HTMLElement>(".passage-source-table")
        ].map((element) => Number.parseFloat(getComputedStyle(element).fontSize));
        return {
          documentOverflow:
            document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
          dividerWidth: Math.round(divider?.getBoundingClientRect().width || 0),
          dockHeight: Math.round(dock?.getBoundingClientRect().height || 0),
          passageFontSize: Number.parseFloat(passageStyle?.fontSize || "0"),
          passageFontWeight: passageStyle?.fontWeight || "",
          questionFontSize: Number.parseFloat(questionStyle?.fontSize || "0"),
          questionPaneWidth: Math.round(questionsPane?.getBoundingClientRect().width || 0),
          overflowing,
          matrixSignatures,
          descriptiveMatching,
          sectionLetters,
          sourceTableFontSizes,
          unresolvedTemplateFallbacks: [
            ...document.querySelectorAll<HTMLElement>(".structured-completion")
          ].filter((element) => element.innerText.includes("_____")).length
        };
      });
      expect(layout.documentOverflow, `${title} Part ${partNumber} document overflow`).toBe(false);
      expect(layout.dividerWidth, `${title} Part ${partNumber} divider width`).toBe(8);
      expect(layout.dockHeight, `${title} Part ${partNumber} bottom navigator height`).toBe(40);
      expect(layout.passageFontSize, `${title} Part ${partNumber} article font size`).toBe(17);
      expect(layout.passageFontWeight, `${title} Part ${partNumber} article font weight`).toBe("500");
      expect(layout.questionFontSize, `${title} Part ${partNumber} question font size`).toBeGreaterThanOrEqual(16);
      expect(layout.questionFontSize, `${title} Part ${partNumber} question font size`).toBeLessThanOrEqual(19);
      expect(layout.overflowing, `${title} Part ${partNumber} component overflow`).toEqual([]);
      for (const matrix of layout.matrixSignatures) {
        expect(
          matrix.headerCells,
          `${title} Part ${partNumber} matrix keeps one prompt column plus answer columns`
        ).toBe(matrix.radioCells + 1);
        expect(matrix.rowHeight, `${title} Part ${partNumber} matrix minimum row density`).toBeGreaterThanOrEqual(49);
      }
      for (const matching of layout.descriptiveMatching) {
        if (layout.questionPaneWidth <= 920) {
          expect(matching.columns, `${title} Part ${partNumber} medium desktop matching stack`).toBe(1);
          expect(matching.questionWidth, `${title} Part ${partNumber} matching question width`).toBeLessThanOrEqual(440);
          expect(matching.bankWidth, `${title} Part ${partNumber} matching option-bank width`).toBeLessThanOrEqual(520);
        } else {
          expect(matching.columns, `${title} Part ${partNumber} wide desktop matching columns`).toBe(2);
        }
      }
      for (const letter of layout.sectionLetters) {
        expect(letter.background, `${title} Part ${partNumber} section-letter background`).toBe("rgba(0, 0, 0, 0)");
        expect(letter.borderWidth, `${title} Part ${partNumber} section-letter border`).toBe("0px");
        expect(letter.fontWeight, `${title} Part ${partNumber} section-letter weight`).toBe("700");
      }
      for (const fontSize of layout.sourceTableFontSizes) {
        expect(fontSize, `${title} Part ${partNumber} source-table font size`).toBeGreaterThanOrEqual(15);
      }
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
