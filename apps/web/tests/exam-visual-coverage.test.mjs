import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "..", "..");
const bankRoot = path.join(repoRoot, "services", "api", "data", "question-bank", "tests");

test("all 58 tests and 174 parts are covered by the shared exam presentation", () => {
  const files = fs.readdirSync(bankRoot).filter((name) => name.endsWith(".json"));
  const tests = files.map((name) =>
    JSON.parse(fs.readFileSync(path.join(bankRoot, name), "utf8"))
  );
  const parts = tests.flatMap((item) => item.parts || []);

  assert.equal(tests.length, 58);
  assert.equal(parts.length, 174);

  for (const part of parts) {
    assert.ok(String(part.article_title || part.title || "").trim(), `${part.id}: missing title`);
    assert.ok(Array.isArray(part.paragraphs) && part.paragraphs.length, `${part.id}: missing paragraphs`);
    assert.ok(Array.isArray(part.groups) && part.groups.length, `${part.id}: missing question groups`);
    for (const paragraph of part.paragraphs) {
      assert.ok(
        String(paragraph.text || "").trim() || paragraph.table,
        `${part.id}: empty paragraph without a source table`
      );
    }
    for (const group of part.groups) {
      assert.ok(Array.isArray(group.questions) && group.questions.length, `${part.id}/${group.id}: empty group`);
    }
  }
});

test("generic Part titles resolve from existing source metadata without duplicating multi-text headings", () => {
  const files = fs.readdirSync(bankRoot).filter((name) => name.endsWith(".json"));
  const parts = files.flatMap((name) =>
    (JSON.parse(fs.readFileSync(path.join(bankRoot, name), "utf8")).parts || [])
  );
  const genericParts = parts.filter((part) => /^Part \d+ reading texts$/i.test(String(part.article_title || "")));

  assert.equal(genericParts.length, 10);
  for (const part of genericParts) {
    assert.ok(String(part.source_article_title || "").trim(), `${part.id}: missing source article title`);
  }

  const singlePassageTitles = new Map([
    ["2137", "LACK OF SLEEP"],
    ["2134", "PTEROSAURS"],
    ["2089", "Marine Ecosystems"],
    ["2512", "Roman Roads"]
  ]);
  for (const [partId, expectedTitle] of singlePassageTitles) {
    const part = genericParts.find((item) => String(item.id) === partId);
    assert.equal(part?.source_article_title, expectedTitle);
    assert.equal(
      (part?.paragraphs || []).some((paragraph) => String(paragraph.text || "").trim().toLowerCase() === expectedTitle.toLowerCase()),
      false,
      `${partId}: single-passage title should be rendered above the body`
    );
  }

  const multiTextPartIds = ["2109", "2076", "2052", "2138", "2139", "2133"];
  for (const partId of multiTextPartIds) {
    const part = genericParts.find((item) => String(item.id) === partId);
    const expectedTitle = String(part?.source_article_title || "").trim().toLowerCase();
    assert.ok(
      (part?.paragraphs || []).some((paragraph) => String(paragraph.text || "").trim().toLowerCase() === expectedTitle),
      `${partId}: multi-text source title should remain at its original paragraph position`
    );
  }
});

test("the shared renderer distinguishes brochure rows before heuristic headings", () => {
  const workbench = fs.readFileSync(path.join(webRoot, "components", "ExamWorkbench.tsx"), "utf8");
  const dashGuard = workbench.indexOf("if (/\\s[-–—]\\s/.test(value)) return false");
  const headingDecision = workbench.indexOf("const titleLike =");

  assert.ok(dashGuard >= 0 && headingDecision > dashGuard);
  assert.match(workbench, /function looksLikePassageCategory/);
  assert.match(workbench, /function passageListingParts/);
  assert.match(workbench, /function resolvedPassageTitle/);
  assert.match(workbench, /GENERIC_PASSAGE_TITLE\.test\(sourceTitle\)\) return ""/);
  assert.match(workbench, /sourceTitleAppearsInBody \? "" : sourceTitle/);
  assert.match(workbench, /className="passage-category-heading passage-unit"/);
  assert.match(workbench, /className="passage-listing passage-unit"/);
  assert.match(workbench, /className="passage-legend passage-unit"/);
});

test("desktop exam defaults and typography follow the verified reading baseline", () => {
  const workbench = fs.readFileSync(path.join(webRoot, "components", "ExamWorkbench.tsx"), "utf8");
  const styles = fs.readFileSync(path.join(webRoot, "app", "globals.css"), "utf8");

  assert.match(workbench, /const READING_FONT_SIZES = \[15, 17, 19, 21, 23\]/);
  assert.match(workbench, /useState\(17\)/);
  assert.match(workbench, /useState\(40\)/);
  assert.match(workbench, /const PANE_RATIO_STORAGE_KEY = "ielts-exam-pane-ratio-v2"/);
  assert.match(workbench, /storedRatioValue !== null && storedRatioValue\.trim\(\) !== ""/);
  assert.match(styles, /\.passage-copy \{[\s\S]*font-family: Inter,[\s\S]*font-size: var\(--reading-font-size, 17px\)[\s\S]*line-height: 1\.75/);
  assert.match(styles, /\.question-card \{[\s\S]*border-bottom: 1px solid var\(--exam-line\)[\s\S]*border-radius: 0/);
  assert.match(styles, /\.question-title-row p \{[^}]*font-weight: 600[^}]*line-height: 1\.75/);
  assert.match(styles, /\.questions-scroll \{[\s\S]*container-name: question-scroll;[\s\S]*container-type: inline-size;/);
  assert.match(styles, /@media \(max-width: 560px\) \{[\s\S]*\.passage-listing \{ display: block; \}/);
});
