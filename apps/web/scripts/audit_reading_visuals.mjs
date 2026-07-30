import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";

const WEB_URL = "http://127.0.0.1:8001";
const API_URL = "http://127.0.0.1:8010";
const OUTPUT_ROOT = path.resolve("..", "..", "output", "reading-visual-audit-2026-07-29");
const SHOT_ROOT = path.join(OUTPUT_ROOT, "parts");

function safeName(value) {
  return String(value).replace(/[^a-z0-9-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function scrollPane(page, selector, ratio) {
  await page.locator(selector).evaluate((element, nextRatio) => {
    element.scrollTop = Math.round((element.scrollHeight - element.clientHeight) * nextRatio);
  }, ratio);
  await page.waitForTimeout(40);
}

async function collectMetrics(page, testId, title, partNumber) {
  return page.evaluate(
    ({ currentTestId, currentTitle, currentPartNumber }) => {
      const visible = (element) => {
        const style = getComputedStyle(element);
        const box = element.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden" && box.width > 0 && box.height > 0;
      };
      const box = (element) => {
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        };
      };
      const fontSizes = (selector) =>
        [...document.querySelectorAll(selector)]
          .filter(visible)
          .map((element) => Number.parseFloat(getComputedStyle(element).fontSize))
          .filter(Number.isFinite);
      const text = (selector) =>
        [...document.querySelectorAll(selector)]
          .map((element) => element.textContent?.trim() || "")
          .filter(Boolean);

      const passagePane = document.querySelector(".passage-pane");
      const questionPane = document.querySelector(".questions-pane");
      const passageScroll = document.querySelector(".passage-pane");
      const questionScroll = document.querySelector(".questions-scroll");
      const dock = document.querySelector(".exam-question-dock");
      const answerControls = [
        ...document.querySelectorAll(
          '.questions-pane input:not([type="hidden"]),.questions-pane select,.questions-pane textarea'
        )
      ].filter(visible);
      const questionBox = questionPane?.getBoundingClientRect();
      const controlsOutsidePane = answerControls
        .map((element) => ({ id: element.id, rect: element.getBoundingClientRect() }))
        .filter(({ rect }) =>
          !questionBox
          || rect.left < questionBox.left - 2
          || rect.right > questionBox.right + 2
        )
        .map(({ id, rect }) => ({
          id,
          left: Math.round(rect.left),
          right: Math.round(rect.right)
        }));
      const overflow = [
        ...document.querySelectorAll(
          ".passage-copy,.questions-scroll,.question-card,.matching-text-group,.matching-interactive-bank,.structured-completion"
        )
      ]
        .filter(visible)
        .filter((element) => element.scrollWidth > element.clientWidth + 3)
        .map((element) => ({
          className: element.className,
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth
        }));
      const passageText = document.querySelector(".passage-copy")?.textContent || "";
      const questionText = document.querySelector(".questions-scroll")?.textContent || "";
      const passageFontSizes = fontSizes(
        ".passage-copy p,.passage-copy li,.passage-copy td,.passage-copy th,.passage-copy .passage-listing"
      );
      const questionFontSizes = fontSizes(
        ".question-title-row p,.answer-options label,.matching-answer-matrix tbody th,.matching-option-card,.completion-line"
      );
      const instructions = text(".question-instructions-copy p");
      const actionInstructionStyles = [
        ...document.querySelectorAll(".question-instructions-copy p")
      ].filter(visible).map((element) => ({
        text: element.textContent?.trim() || "",
        italic: getComputedStyle(element).fontStyle === "italic"
      }));
      const matrixTables = [...document.querySelectorAll(".matching-answer-matrix")].map((table) => ({
        columns: table.tHead?.rows[0]?.cells.length || 0,
        rows: table.tBodies[0]?.rows.length || 0,
        width: Math.round(table.getBoundingClientRect().width),
        fontSize: Number.parseFloat(getComputedStyle(table).fontSize),
        fontWeight: getComputedStyle(table).fontWeight
      }));
      const sourceTables = [...document.querySelectorAll(".passage-source-table")].map((table) => ({
        width: Math.round(table.getBoundingClientRect().width),
        scrollWidth: table.scrollWidth,
        clientWidth: table.clientWidth,
        fontSize: Number.parseFloat(getComputedStyle(table).fontSize),
        caption: table.querySelector("caption")?.textContent?.trim() || ""
      }));

      return {
        testId: currentTestId,
        title: currentTitle,
        partNumber: currentPartNumber,
        url: location.href,
        viewport: { width: innerWidth, height: innerHeight },
        documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 3,
        paneBoxes: {
          passage: box(passagePane),
          questions: box(questionPane),
          dock: box(dock)
        },
        scroll: {
          passageHeight: passageScroll?.scrollHeight || 0,
          passageViewport: passageScroll?.clientHeight || 0,
          questionHeight: questionScroll?.scrollHeight || 0,
          questionViewport: questionScroll?.clientHeight || 0
        },
        counts: {
          passageUnits: document.querySelectorAll(".passage-copy .passage-unit").length,
          passageHeadings: document.querySelectorAll(".passage-copy h1,.passage-copy h2").length,
          sourceTables: sourceTables.length,
          questionGroups: document.querySelectorAll(".question-group").length,
          questionCards: document.querySelectorAll(".question-card").length,
          answerControls: answerControls.length,
          matrices: matrixTables.length,
          matchingBanks: document.querySelectorAll(".matching-interactive-bank").length,
          completionBlocks: document.querySelectorAll(".structured-completion").length
        },
        textChecks: {
          passageLength: passageText.trim().length,
          questionLength: questionText.trim().length,
          replacementCharacter: /�/.test(`${passageText}${questionText}`),
          mojibake: /(?:Ã.|Â.|â€™|â€œ|â€|ï¿½)/.test(`${passageText}${questionText}`),
          objectLeak: /\[object Object\]|\bundefined\b|\bnull\b/.test(`${passageText}${questionText}`),
          unresolvedBlank: [...document.querySelectorAll(".structured-completion")]
            .some((element) => /_{5,}/.test(element.textContent || "")),
          genericVisibleTitle: /^Part \d+ reading texts$/im.test(passageText),
          instructions
        },
        typography: {
          passageMin: passageFontSizes.length ? Math.min(...passageFontSizes) : 0,
          passageMax: passageFontSizes.length ? Math.max(...passageFontSizes) : 0,
          questionMin: questionFontSizes.length ? Math.min(...questionFontSizes) : 0,
          questionMax: questionFontSizes.length ? Math.max(...questionFontSizes) : 0,
          actionInstructionStyles
        },
        overflow,
        controlsOutsidePane,
        matrixTables,
        sourceTables
      };
    },
    { currentTestId: testId, currentTitle: title, currentPartNumber: partNumber }
  );
}

function anomalyMessages(metrics) {
  const failures = [];
  if (metrics.documentOverflow) failures.push("document-horizontal-overflow");
  if (!metrics.paneBoxes.passage || !metrics.paneBoxes.questions || !metrics.paneBoxes.dock) {
    failures.push("missing-desktop-pane");
  }
  if (metrics.counts.passageUnits === 0 || metrics.textChecks.passageLength < 20) {
    failures.push("empty-or-too-short-passage");
  }
  if (metrics.counts.questionGroups === 0 || metrics.textChecks.questionLength < 20) {
    failures.push("empty-or-too-short-questions");
  }
  if (metrics.counts.answerControls === 0) failures.push("missing-answer-controls");
  if (metrics.textChecks.replacementCharacter) failures.push("replacement-character");
  if (metrics.textChecks.mojibake) failures.push("mojibake");
  if (metrics.textChecks.objectLeak) failures.push("object-leak");
  if (metrics.textChecks.unresolvedBlank) failures.push("unresolved-template-blank");
  if (metrics.textChecks.genericVisibleTitle) failures.push("generic-title-visible");
  if (metrics.typography.passageMin && metrics.typography.passageMin < 15) {
    failures.push(`passage-font-too-small:${metrics.typography.passageMin}`);
  }
  if (metrics.typography.questionMin && metrics.typography.questionMin < 15) {
    failures.push(`question-font-too-small:${metrics.typography.questionMin}`);
  }
  if (metrics.overflow.length) failures.push(`component-overflow:${metrics.overflow.length}`);
  if (metrics.controlsOutsidePane.length) {
    failures.push(`answer-controls-outside-pane:${metrics.controlsOutsidePane.length}`);
  }
  for (const matrix of metrics.matrixTables) {
    if (matrix.fontSize < 15) failures.push(`matrix-font-too-small:${matrix.fontSize}`);
    if (matrix.fontWeight !== "400") failures.push(`matrix-weight:${matrix.fontWeight}`);
  }
  for (const table of metrics.sourceTables) {
    if (table.fontSize < 15) failures.push(`source-table-font-too-small:${table.fontSize}`);
  }
  return failures;
}

await fs.mkdir(SHOT_ROOT, { recursive: true });
const index = await fetchJson(`${API_URL}/api/v1/question-bank/tests`);
if (index.items.length !== 58) throw new Error(`Expected 58 tests, received ${index.items.length}`);

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("dialog", (dialog) => dialog.accept());
await page.goto(`${WEB_URL}/practice`);
await page.locator(".test-card").first().waitFor();

const metrics = [];
for (let testIndex = 0; testIndex < index.items.length; testIndex += 1) {
  const item = index.items[testIndex];
  const payload = await fetchJson(
    `${API_URL}/api/v1/question-bank/tests/${encodeURIComponent(item.id)}`
  );
  for (const part of payload.parts) {
    const card = page.locator(".test-card").filter({ hasText: payload.title });
    if (await card.count() !== 1) throw new Error(`Cannot resolve UI card: ${payload.title}`);
    await card.getByRole("button", { name: `Part ${part.number}`, exact: true }).click();
    await page.locator(".exam-workbench").waitFor();

    await scrollPane(page, ".passage-pane", 0);
    await scrollPane(page, ".questions-scroll", 0);
    const slug = `${safeName(item.id)}-part-${part.number}`;
    await page.screenshot({
      path: path.join(SHOT_ROOT, `${slug}-top.jpg`),
      type: "jpeg",
      quality: 58
    });

    await scrollPane(page, ".passage-pane", 0.5);
    await scrollPane(page, ".questions-scroll", 0.5);
    await page.screenshot({
      path: path.join(SHOT_ROOT, `${slug}-middle.jpg`),
      type: "jpeg",
      quality: 58
    });

    await scrollPane(page, ".passage-pane", 1);
    await scrollPane(page, ".questions-scroll", 1);
    await page.screenshot({
      path: path.join(SHOT_ROOT, `${slug}-bottom.jpg`),
      type: "jpeg",
      quality: 58
    });

    const partMetrics = await collectMetrics(page, item.id, payload.title, part.number);
    metrics.push({ ...partMetrics, anomalies: anomalyMessages(partMetrics) });
    await page.getByRole("button", { name: "退出", exact: true }).click();
    await page.locator(".test-card").first().waitFor();
  }
  process.stdout.write(`\rvisual audit ${testIndex + 1}/${index.items.length} tests`);
}
process.stdout.write("\n");

await browser.close();
const anomalies = metrics.filter((item) => item.anomalies.length);
const summary = {
  generatedAt: new Date().toISOString(),
  tests: index.items.length,
  parts: metrics.length,
  screenshots: metrics.length * 3,
  pageErrors,
  anomalyCount: anomalies.length,
  anomalyParts: anomalies.map((item) => ({
    testId: item.testId,
    title: item.title,
    partNumber: item.partNumber,
    anomalies: item.anomalies
  }))
};
await fs.writeFile(path.join(OUTPUT_ROOT, "metrics.json"), JSON.stringify(metrics, null, 2));
await fs.writeFile(path.join(OUTPUT_ROOT, "summary.json"), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary, null, 2));
