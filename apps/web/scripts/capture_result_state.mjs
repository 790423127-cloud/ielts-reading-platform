import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "@playwright/test";

const WEB_URL = "http://127.0.0.1:8001";
const outputDir = join(process.cwd(), "output", "playwright", "result-state-audit");
await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
page.on("dialog", (dialog) => dialog.accept());

try {
  await page.goto(`${WEB_URL}/practice`);
  const card = page.locator(".test-card").filter({ hasText: "剑雅5 Test B" });
  await card.locator(".test-actions .secondary-button").click();
  await page.locator(".exam-workbench").waitFor();

  const firstTextInput = page.locator('.questions-pane input:not([type]),.questions-pane input[type="text"]').first();
  if (await firstTextInput.count()) await firstTextInput.fill("wrong answer");
  await page.locator(".exam-submit-button").click();
  await page.locator(".result-page").waitFor({ timeout: 30_000 });

  await page.screenshot({ path: join(outputDir, "result-top.png") });
  const sourceReview = page.locator("#result-source-review");
  await sourceReview.scrollIntoViewIfNeeded();
  await page.screenshot({ path: join(outputDir, "result-source-review-viewport.png") });
  await page.locator(".result-source-split").screenshot({ path: join(outputDir, "result-source-split.png") });
  const immediatePerformanceSections = await page.locator("#result-performance").count();
  const legacyQuestionReviewSections = await page.locator("#result-review,.result-question-card").count();
  const firstAnalysisButton = page.locator(".result-source-analysis-actions button").first();
  await firstAnalysisButton.click();
  await page.locator(".result-analysis-dialog").waitFor();
  const selectedAnswerSentenceMarks = await page.locator('mark[data-answer-sentence]').count();
  const aiTeacherEmbedded = await page.locator(".result-analysis-dialog .ai-teacher-panel").count() === 1;
  await page.locator(".result-analysis-dialog").screenshot({ path: join(outputDir, "result-question-analysis-dialog.png") });
  await page.locator('.result-analysis-dialog button[aria-label="关闭解析"]').click();
  await page.locator('.result-source-view-tools button[role="switch"]').filter({ hasText: "答案句" }).click();
  const allAnswerSentenceMarks = await page.locator('mark[data-answer-sentence]').count();
  await page.locator(".result-source-split").screenshot({ path: join(outputDir, "result-answer-sentences.png") });
  await page.locator('.result-source-view-tools button[role="switch"]').filter({ hasText: "翻译" }).click();
  const visibleTranslationBlocks = await page.locator(".result-passage-translation").count();
  const translationSamples = await page.locator(".result-passage-translation").evaluateAll((elements) => elements.slice(0, 5).map((element) => ({
    text: element.textContent,
    top: Math.round(element.getBoundingClientRect().top),
    previous: element.previousElementSibling?.textContent,
    parent: element.parentElement?.tagName,
  })));
  await page.locator(".result-source-split").screenshot({ path: join(outputDir, "result-translations.png") });
  const resultPartTabs = page.locator(".result-source-dock-label");
  let partSwitchWorked = null;
  if (await resultPartTabs.count() > 1) {
    await resultPartTabs.nth(1).click();
    partSwitchWorked = (await page.locator(".result-source-active-heading strong").innerText()).trim() === "Part 2";
  }
  const metrics = await page.evaluate(({ immediatePerformanceSections, legacyQuestionReviewSections, partSwitchWorked, selectedAnswerSentenceMarks, allAnswerSentenceMarks, visibleTranslationBlocks, translationSamples, aiTeacherEmbedded }) => {
    const box = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return { width: Math.round(rect.width), height: Math.round(rect.height) };
    };
    const resultPage = document.querySelector(".result-page");
    const split = document.querySelector(".result-source-split");
    return {
      documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 3,
      resultPage: box(".result-page"),
      hero: box(".result-hero"),
      sourceSplit: box(".result-source-split"),
      sourcePassage: box(".result-source-passage"),
      sourceAnswers: box(".result-source-answers"),
      pageScrollHeight: resultPage?.scrollHeight || 0,
      splitOverflow: split ? split.scrollWidth > split.clientWidth + 3 : null,
      disabledReviewControls: document.querySelectorAll(".result-source-question-group :disabled").length,
      partSwitchWorked,
      immediatePerformanceSections,
      legacyQuestionReviewSections,
      selectedAnswerSentenceMarks,
      allAnswerSentenceMarks,
      visibleTranslationBlocks,
      translationSamples,
      aiTeacherEmbedded,
    };
  }, { immediatePerformanceSections, legacyQuestionReviewSections, partSwitchWorked, selectedAnswerSentenceMarks, allAnswerSentenceMarks, visibleTranslationBlocks, translationSamples, aiTeacherEmbedded });
  await page.goto(`${WEB_URL}/history`);
  await page.getByRole("button", { name: "详细报告" }).first().click();
  await page.locator(".result-page").waitFor();
  metrics.historicalPerformanceSections = await page.locator("#result-performance").count();
  metrics.historicalLegacyQuestionReviewSections = await page.locator("#result-review,.result-question-card").count();
  metrics.historicalAnalysisButtons = await page.locator(".result-source-analysis-actions button").count();
  await page.screenshot({ path: join(outputDir, "result-history-report.png"), fullPage: true });
  await writeFile(join(outputDir, "metrics.json"), `${JSON.stringify(metrics, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ outputDir, metrics }, null, 2));
} finally {
  await browser.close();
}
