import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("full-text matching restores the legacy option-bank and answer-slot interaction", () => {
  assert.match(workbench, /function MatchingTextGroup/);
  assert.match(workbench, /matchingHasDescriptions \? \(/);
  assert.match(workbench, /matching-interactive-bank/);
  assert.match(workbench, /matching-answer-slot/);
  assert.match(workbench, /gridTemplateColumns: `minmax\(0, \$\{paneRatio\}fr\) 7px minmax\(0, \$\{100 - paneRatio\}fr\)`/);
  assert.match(workbench, /className=\{`matching-option-card[\s\S]*?draggable[\s\S]*?onDragStart=/);
  assert.match(workbench, /dataTransfer\.setData\("text\/plain", option\.code\)/);
  assert.match(workbench, /assignAnswer\(id, selectedCode\)/);
  assert.match(workbench, /optionReuse/);
  assert.match(workbench, /restoreInstructionOptionText/);
  assert.match(css, /\.passage-pane, \.questions-pane \{[\s\S]*?min-width: 0;[\s\S]*?overflow-x: hidden;/);
  assert.match(css, /\.matching-question-row/);
  assert.match(css, /grid-template-areas: "help help" "questions bank"/);
  assert.match(css, /\.matching-question-list \{[^}]*grid-area: questions/);
  assert.match(css, /\.matching-interactive-bank \{[\s\S]*?grid-area: bank/);
});

test("letter-only matching keeps the compact matrix renderer", () => {
  assert.match(workbench, /useMatchingMatrix/);
  assert.match(workbench, /matching-answer-matrix/);
  assert.match(css, /\.matching-answer-matrix/);
});

test("completion and short-answer questions use the source inline template or an inline answer box", () => {
  assert.match(workbench, /"diagram_label_completion", "short_answer"/);
  assert.match(workbench, /const inlineCompletion = family === "completion"/);
  assert.match(workbench, /className="inline-question-answer"/);
  assert.match(css, /\.inline-question-answer input/);
});

test("question instructions retain line hierarchy and emphasize answer constraints", () => {
  assert.match(workbench, /function QuestionInstructions/);
  assert.match(workbench, /function normalizeInstructionDetails/);
  assert.match(workbench, /correct option/);
  assert.match(workbench, /question-instructions-heading/);
  assert.match(workbench, /INSTRUCTION_EMPHASIS/);
  assert.match(css, /\.question-instructions-copy p:first-child/);
});

test("each multiple-choice question keeps its own option list before group fallbacks", () => {
  assert.match(workbench, /function optionsFor[\s\S]*?if \(question\.options\?\.length\)[\s\S]*?if \(group\.normalized_options\?\.length\)/);
});

test("question typography is consistent across prompts, matching banks, and completion tables", () => {
  assert.match(css, /--question-content-size:/);
  assert.match(css, /\.matching-option-card \{[\s\S]*?font-size: 1em;/);
  assert.match(css, /\.completion-table-scroll table \{[^}]*font-size: 1em;/);
  assert.match(workbench, /function displayMarkup/);
});

test("bottom navigation groups question numbers by passage and retains status navigation", () => {
  assert.match(workbench, /dock-section-strip/);
  assert.match(workbench, /<strong>Passage \{part\.number\}<\/strong>/);
  assert.match(workbench, /\{completed\} of \{partRows\.length\}/);
  assert.match(workbench, /dock-step-buttons/);
  assert.match(css, /\.dock-section-label/);
  assert.match(css, /\.dock-question-list button\.current/);
  assert.match(css, /\.dock-question-list button\.flagged/);
});
