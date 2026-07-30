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
  assert.match(workbench, /gridTemplateColumns: `minmax\(0, \$\{paneRatio\}fr\) 8px minmax\(0, \$\{100 - paneRatio\}fr\)`/);
  assert.match(workbench, /className=\{`matching-option-card[\s\S]*?draggable[\s\S]*?onDragStart=/);
  assert.match(workbench, /dataTransfer\.setData\("text\/plain", option\.code\)/);
  assert.match(workbench, /assignAnswer\(id, selectedCode\)/);
  assert.match(workbench, /placeholder=\{`\$\{questionNumber\(question\)\} 拖拽或输入选项字母`\}/);
  assert.match(workbench, /else if \(optionMap\.has\(nextCode\)\) assignAnswer\(id, nextCode\)/);
  assert.match(workbench, /const chosenText = chosen \? optionDisplayText\(chosen\) : ""/);
  assert.match(workbench, /matching-answer-description/);
  assert.match(workbench, /if \(chosen\) event\.currentTarget\.select\(\)/);
  assert.match(css, /\.matching-answer-slot\.filled \{[\s\S]*?grid-template-columns: max-content minmax\(0, 1fr\)/);
  assert.match(css, /\.matching-answer-description \{/);
  assert.match(workbench, /optionReuse/);
  assert.match(workbench, /restoreInstructionOptionText/);
  assert.match(css, /\.passage-pane, \.questions-pane \{[\s\S]*?min-width: 0;[\s\S]*?overflow-x: hidden;/);
  assert.match(css, /\.matching-question-row/);
  assert.match(css, /grid-template-areas:\s*"help help"\s*"questions bank"/);
  assert.match(css, /grid-template-columns: minmax\(260px, \.78fr\) minmax\(360px, 1\.22fr\)/);
  assert.match(css, /@container question-scroll \(max-width: 920px\)/);
  assert.match(css, /grid-template-areas: "help" "questions" "bank"/);
  assert.match(css, /\.matching-question-list \{[^}]*grid-area: questions/);
  assert.match(css, /\.matching-interactive-bank \{[\s\S]*?grid-area: bank/);
});

test("letter-only matching follows the benchmark matrix while descriptive matching keeps the option bank", () => {
  assert.match(workbench, /const matchingHasDescriptions = matching && groupOptions\.some/);
  assert.match(workbench, /const useMatchingMatrix = matching && groupOptions\.length > 0/);
  assert.match(workbench, /text\.localeCompare\(option\.code/);
  assert.match(workbench, /useMatchingMatrix \? \(/);
  assert.match(workbench, /matching-answer-matrix/);
  assert.doesNotMatch(workbench, /<th scope="col">标记<\/th>/);
  assert.match(workbench, /matchingHasDescriptions \? \(/);
  assert.match(css, /\.matching-answer-matrix/);
  assert.match(css, /\.matrix-answer-radio/);
});

test("completion and short-answer questions use the source inline template or an inline answer box", () => {
  assert.match(workbench, /"diagram_label_completion", "short_answer"/);
  assert.match(workbench, /function structuredTemplateParts/);
  assert.match(workbench, /questionPlaceholder/);
  assert.doesNotMatch(workbench, /split\(\/\(\\\$\[\^\$\]\+\\\$\)\/g\)/);
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
  assert.match(workbench, /INSTRUCTION_ACTION_LINE/);
  assert.match(workbench, /TRUE\|FALSE\|NOT GIVEN/);
  assert.match(css, /\.question-instructions-copy \.instruction-action-line/);
});

test("question option codes retain their order and recover missing display text from the group", () => {
  assert.match(workbench, /const questionOptions = restoreInstructionOptionText/);
  assert.match(workbench, /const groupOptionsByCode = new Map/);
  assert.match(workbench, /optionDisplayText\(option\)[\s\S]*?groupOptionsByCode\.get\(option\.code\)/);
});

test("question typography is consistent across prompts, matching banks, and completion tables", () => {
  assert.match(css, /--question-content-size:/);
  assert.match(css, /\.matching-option-card \{[\s\S]*?font-size: 1em;/);
  assert.match(css, /\.completion-table-scroll table \{[^}]*font-size: 1em;/);
  assert.match(workbench, /function displayMarkup/);
});

test("bottom navigation groups question numbers by passage and retains status navigation", () => {
  assert.match(workbench, /dock-section-strip/);
  assert.match(workbench, /isActivePart \? `P\$\{part\.number\}` : `Passage \$\{part\.number\}`/);
  assert.match(workbench, /!isActivePart \? <span>\{completed\} of \{partRows\.length\}<\/span> : null/);
  assert.match(workbench, /\{isActivePart \? \(\s*<div className="dock-question-list">/);
  assert.match(workbench, /dock-step-buttons/);
  assert.match(css, /\.exam-question-dock \{[^}]*height: 40px/);
  assert.match(css, /\.dock-section \{[^}]*flex: 1 1 33\.333%/);
  assert.match(css, /\.dock-section-label/);
  assert.match(css, /\.dock-question-list button\.current/);
  assert.match(css, /\.dock-question-list button\.flagged/);
});
