import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "@playwright/test";

const WEB_URL = "http://127.0.0.1:8001";
const API_URL = "http://127.0.0.1:8010";
const OUTPUT_ROOT = process.env.READING_VISUAL_OUTPUT
  ? path.resolve(process.env.READING_VISUAL_OUTPUT)
  : path.resolve("..", "..", "output", "reading-visual-audit-2026-08-01");
const SHOT_ROOT = path.join(OUTPUT_ROOT, "parts");

function safeName(value) {
  return String(value).replace(/[^a-z0-9-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

function sourceBaselineExpected(testId) {
  const book = Number.parseInt(String(testId).match(/^b(\d+)-/)?.[1] || "0", 10);
  return book >= 5 && book <= 20;
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
        .map((element) => ({
          id: element.id,
          rect: element.getBoundingClientRect(),
          scrollContainer: element.closest(".source-matching-matrix-wrap")
        }))
        .filter(({ rect, scrollContainer }) => {
          const outsidePane = !questionBox
            || rect.left < questionBox.left - 2
            || rect.right > questionBox.right + 2;
          if (!outsidePane) return false;
          if (!scrollContainer) return true;
          const overflowX = getComputedStyle(scrollContainer).overflowX;
          return !(scrollContainer.scrollWidth > scrollContainer.clientWidth + 3
            && (overflowX === "auto" || overflowX === "scroll"));
        })
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
        ".question-title-row p,.answer-options label,.matching-answer-matrix tbody th,.matching-option-card,.completion-line,.source-question-row,.source-questions-content"
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
      const sourceMatrixTables = [...document.querySelectorAll(".source-matching-matrix")].map((table) => ({
        columns: table.tHead?.rows[0]?.cells.length || 0,
        rows: table.tBodies[0]?.rows.length || 0,
        width: Math.round(table.getBoundingClientRect().width),
        fontSize: Number.parseFloat(getComputedStyle(table).fontSize)
      }));
      const sourceInteractionBlocks = [...document.querySelectorAll(".source-question-block")].map((block) => {
        const type = Number(block.getAttribute("data-source-question-type") || -1);
        return {
          type,
          mode: block.getAttribute("data-source-interaction-mode") || "",
          textInputs: block.querySelectorAll('input:not([type]),input[type="text"]').length,
          radios: block.querySelectorAll('input[type="radio"]').length,
          checkboxes: block.querySelectorAll('input[type="checkbox"]').length,
          selects: block.querySelectorAll("select").length,
          matrices: block.querySelectorAll(".source-matching-matrix").length
        };
      });
      const sourceInteractionIssues = sourceInteractionBlocks.flatMap((block, index) => {
        const prefix = `source-block-${index}-type-${block.type}`;
        if (block.type === 0 && block.textInputs === 0) return [`${prefix}-missing-text-input`];
        if (block.type === 1 && block.radios === 0) return [`${prefix}-missing-radio`];
        if (block.type === 2 && block.checkboxes === 0) return [`${prefix}-missing-checkbox`];
        if (block.type === 3 && block.radios === 0) return [`${prefix}-missing-judgement-radio`];
        if (block.type === 4 && (block.matrices !== 1 || block.radios === 0)) return [`${prefix}-missing-matrix`];
        if (block.type === 4 && block.selects > 0) return [`${prefix}-obsolete-select`];
        return [];
      });
      const rawSourceTables = [...document.querySelectorAll(".passage-source-html table")].map((table) => ({
        width: Math.round(table.getBoundingClientRect().width),
        scrollWidth: table.scrollWidth,
        clientWidth: table.clientWidth,
        rows: table.rows.length,
        cells: table.querySelectorAll("th,td").length
      }));
      const sourceVisualName = document.querySelector(".passage-source-html")
        ?.getAttribute("data-source-visual-name") || "";

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
          sourceHtmlElements: document.querySelectorAll(".passage-source-html > *").length,
          sourceQuestionBlocks: document.querySelectorAll(".source-question-block").length,
          passageHeadings: document.querySelectorAll(".passage-copy h1,.passage-copy h2").length,
          sourceTables: sourceTables.length,
          rawSourceTables: rawSourceTables.length,
          questionGroups: document.querySelectorAll(".question-group").length,
          questionCards: document.querySelectorAll(".question-card").length,
          answerControls: answerControls.length,
          matrices: matrixTables.length,
          sourceMatrices: sourceMatrixTables.length,
          sourceType4Blocks: sourceInteractionBlocks.filter((block) => block.type === 4).length,
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
          instructions,
          sourceVisualName,
          sourceHtmlEnabled: document.querySelector(".exam-workbench")
            ?.getAttribute("data-source-visual") === "true"
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
        sourceMatrixTables,
        sourceInteractionBlocks,
        sourceInteractionIssues,
        sourceTables,
        rawSourceTables
      };
    },
    { currentTestId: testId, currentTitle: title, currentPartNumber: partNumber }
  );
}

function anomalyMessages(metrics, expectsSourceBaseline) {
  const failures = [];
  if (metrics.documentOverflow) failures.push("document-horizontal-overflow");
  if (!metrics.paneBoxes.passage || !metrics.paneBoxes.questions || !metrics.paneBoxes.dock) {
    failures.push("missing-desktop-pane");
  }
  if ((metrics.counts.passageUnits === 0 && metrics.counts.sourceHtmlElements === 0)
    || metrics.textChecks.passageLength < 20) {
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
  if (expectsSourceBaseline && !metrics.textChecks.sourceHtmlEnabled) {
    failures.push("missing-source-html-baseline");
  }
  if (expectsSourceBaseline && !metrics.textChecks.sourceVisualName) {
    failures.push("missing-source-visual-name");
  }
  if (expectsSourceBaseline && metrics.counts.sourceQuestionBlocks === 0) {
    failures.push("missing-source-question-renderer");
  }
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
  if (metrics.sourceInteractionIssues.length) {
    failures.push(...metrics.sourceInteractionIssues);
  }
  for (const matrix of metrics.sourceMatrixTables) {
    if (matrix.fontSize < 15) failures.push(`source-matrix-font-too-small:${matrix.fontSize}`);
    if (matrix.columns < 3 || matrix.rows < 1) failures.push("source-matrix-invalid-shape");
  }
  for (const table of metrics.rawSourceTables) {
    if (table.scrollWidth > table.clientWidth + 3) failures.push("raw-source-table-overflow");
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
    const expectsSourceBaseline = sourceBaselineExpected(item.id);
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
    metrics.push({
      ...partMetrics,
      baselineStatus: expectsSourceBaseline ? "source-baseline" : "no-ieltsbro-baseline",
      anomalies: anomalyMessages(partMetrics, expectsSourceBaseline)
    });
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
  sourceBaselineParts: metrics.filter((item) => item.baselineStatus === "source-baseline").length,
  noBaselineParts: metrics.filter((item) => item.baselineStatus === "no-ieltsbro-baseline").length,
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
