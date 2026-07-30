import { expect, test } from "@playwright/test";

type PublicQuestion = {
  id: string;
};

type PublicGroup = {
  question_subtype: string;
  required_choices?: number;
  shared_response?: boolean;
  questions: PublicQuestion[];
};

type PublicPart = {
  number: number;
  groups: PublicGroup[];
};

type PublicTest = {
  id: string;
  title: string;
  parts: PublicPart[];
};

type Representative = {
  testTitle: string;
  partNumber: number;
  questionId: string;
  requiredChoices: number;
};

const API_BASE_URL = "http://127.0.0.1:8010";

test("every question subtype accepts an answer through its real desktop control", async ({
  page,
  request
}) => {
  const indexResponse = await request.get(`${API_BASE_URL}/api/v1/question-bank/tests`);
  expect(indexResponse.ok()).toBeTruthy();
  const index = await indexResponse.json() as { items: Array<{ id: string }> };
  const representatives = new Map<string, Representative>();

  for (const item of index.items) {
    const response = await request.get(
      `${API_BASE_URL}/api/v1/question-bank/tests/${encodeURIComponent(item.id)}`
    );
    expect(response.ok(), item.id).toBeTruthy();
    const payload = await response.json() as PublicTest;
    for (const part of payload.parts) {
      for (const group of part.groups) {
        const firstQuestion = group.questions[0];
        if (!firstQuestion || representatives.has(group.question_subtype)) continue;
        representatives.set(group.question_subtype, {
          testTitle: payload.title,
          partNumber: part.number,
          questionId: String(firstQuestion.id),
          requiredChoices: Number(
            group.required_choices
              || (group.shared_response ? group.questions.length : 1)
          )
        });
      }
    }
  }

  expect([...representatives.keys()].sort()).toEqual([
    "diagram_label_completion",
    "flow_chart_completion",
    "matching_features",
    "matching_headings",
    "matching_information",
    "matching_names",
    "matching_places",
    "matching_sentence_endings",
    "multiple_choice_multiple",
    "multiple_choice_single",
    "note_completion",
    "sentence_completion",
    "short_answer",
    "summary_completion",
    "table_completion",
    "true_false_not_given"
  ]);

  await page.goto("/practice");
  await expect(page.locator(".test-card")).toHaveCount(58);

  for (const [subtype, representative] of representatives) {
    const card = page.locator(".test-card").filter({ hasText: representative.testTitle });
    await expect(card, `${subtype} test card`).toHaveCount(1);
    await card
      .getByRole("button", { name: `Part ${representative.partNumber}`, exact: true })
      .click();

    const control = page.locator(`[id="question-${representative.questionId}"]`);
    await expect(control, `${subtype} answer control`).toHaveCount(1);
    await control.scrollIntoViewIfNeeded();

    const select = control.locator("select");
    const checkbox = control.locator('input[type="checkbox"]');
    const radio = control.locator('input[type="radio"]');
    const textInput = control.locator('input:not([type]), input[type="text"]');

    if (await select.count()) {
      const values = await select.locator("option").evaluateAll((options) =>
        options.map((option) => (option as HTMLOptionElement).value).filter(Boolean)
      );
      expect(values.length, `${subtype} selectable options`).toBeGreaterThan(0);
      await select.selectOption(values[0]);
      await expect(select).toHaveValue(values[0]);
    } else if (await checkbox.count()) {
      const checkboxCount = await checkbox.count();
      for (
        let index = 0;
        index < Math.min(representative.requiredChoices, checkboxCount);
        index += 1
      ) {
        await checkbox.nth(index).check({ force: true });
        await expect(checkbox.nth(index)).toBeChecked();
      }
    } else if (await radio.count()) {
      await radio.first().check({ force: true });
      await expect(radio.first()).toBeChecked();
    } else {
      await expect(textInput, `${subtype} text entry`).toHaveCount(1);
      const matchingSlotCount = await control.locator(".matching-answer-slot").count();
      let answer = "sample";
      if (matchingSlotCount) {
        const optionCodes = page.locator(".matching-option-card > strong");
        expect(await optionCodes.count(), `${subtype} matching option codes`).toBeGreaterThan(0);
        answer = String(await optionCodes.first().textContent()).trim();
      }
      await textInput.fill(answer);
      await expect(textInput).toHaveValue(answer);
    }

    await expect(
      control,
      `${subtype} answered state`
    ).toHaveClass(/answered|filled/);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await expect(page.locator(".test-card")).toHaveCount(58);
  }
});

test("judgement answers stay visually clean and annotations restore only from a manual draft", async ({
  page
}) => {
  const openFreshPart = async () => {
    const card = page.locator(".test-card").filter({ hasText: "剑雅5 Test A" });
    await expect(card).toHaveCount(1);
    await card.getByRole("button", { name: "Part 1", exact: true }).click();
    await expect(page.locator(".question-card--judgement")).toHaveCount(7);
  };

  await page.goto("/practice");
  await openFreshPart();

  const firstCard = page.locator(".question-card--judgement").first();
  await firstCard.getByRole("radio", { name: "NOT GIVEN", exact: true }).check({ force: true });
  const answeredStyles = await firstCard.evaluate((card) => {
    const title = card.querySelector<HTMLElement>(".question-title-row");
    const selected = card.querySelector<HTMLElement>(".answer-options label.selected");
    if (!title || !selected) throw new Error("answered judgement presentation is incomplete");
    return {
      cardBoxShadow: getComputedStyle(card).boxShadow,
      titleBorderLeftWidth: getComputedStyle(title).borderLeftWidth,
      titleBackground: getComputedStyle(title).backgroundColor,
      selectedBackground: getComputedStyle(selected).backgroundColor,
      selectedBoxShadow: getComputedStyle(selected).boxShadow
    };
  });
  expect(answeredStyles).toEqual({
    cardBoxShadow: "none",
    titleBorderLeftWidth: "0px",
    titleBackground: "rgba(0, 0, 0, 0)",
    selectedBackground: "rgba(0, 0, 0, 0)",
    selectedBoxShadow: "none"
  });

  await page.evaluate(() => {
    const unit = [...document.querySelectorAll<HTMLElement>(".passage-copy .passage-unit")]
      .find((element) => element.textContent?.includes("Our key for clothing specials in July"));
    if (!unit) throw new Error("highlight source text not found");
    const walker = document.createTreeWalker(unit, NodeFilter.SHOW_TEXT);
    const textNode = walker.nextNode() as Text | null;
    if (!textNode) throw new Error("highlight source text node not found");
    const start = textNode.data.indexOf("clothing specials");
    if (start < 0) throw new Error("highlight target text not found");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "clothing specials".length);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
  });
  await page.getByRole("button", { name: "高亮", exact: true }).click();
  await expect.poll(() => page.evaluate(() => CSS.highlights.has("reading-highlight"))).toBe(true);

  await page.evaluate(() => {
    const unit = [...document.querySelectorAll<HTMLElement>(".passage-copy .passage-unit")]
      .find((element) => element.textContent?.includes("Our key for clothing specials in July"));
    if (!unit) throw new Error("second highlight source text not found");
    const walker = document.createTreeWalker(unit, NodeFilter.SHOW_TEXT);
    const textNode = walker.nextNode() as Text | null;
    if (!textNode) throw new Error("second highlight source text node not found");
    const start = textNode.data.indexOf("specials");
    if (start < 0) throw new Error("second highlight target text not found");
    const range = document.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, start + "specials".length);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    document.dispatchEvent(new Event("selectionchange", { bubbles: true }));
  });
  await page.getByRole("button", { name: "二次高亮", exact: true }).click();
  await expect.poll(
    () => page.evaluate(() => CSS.highlights.has("reading-highlight-secondary"))
  ).toBe(true);

  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page.locator(".exam-notice")).toContainText("草稿已手动保存");

  await page.reload();
  await page.getByRole("button", { name: /管理草稿/ }).click();
  const draft = page.getByRole("dialog").locator("article").filter({ hasText: "剑雅5 Test A" });
  await expect(draft).toContainText("标注 2 条");
  await draft.getByRole("button", { name: "继续草稿", exact: true }).click();
  await expect(page.locator(".answer-options label.selected")).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => CSS.highlights.has("reading-highlight"))).toBe(true);
  await expect.poll(
    () => page.evaluate(() => CSS.highlights.has("reading-highlight-secondary"))
  ).toBe(true);

  await page.reload();
  await openFreshPart();
  await expect(page.locator(".answer-options label.selected")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => CSS.highlights.has("reading-highlight"))).toBe(false);
  await expect.poll(
    () => page.evaluate(() => CSS.highlights.has("reading-highlight-secondary"))
  ).toBe(false);
  await expect(page.getByRole("button", { name: "保存草稿", exact: true })).toBeDisabled();
});
