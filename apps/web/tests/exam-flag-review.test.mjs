import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("every exam rendering mode exposes a persistent current-question flag control", () => {
  assert.match(workbench, /className=\{activeQuestionFlagged \? "dock-flag-button active" : "dock-flag-button"\}/);
  assert.match(workbench, /aria-pressed=\{activeQuestionFlagged\}/);
  assert.match(workbench, /aria-label=\{activeQuestionFlagged \? "取消当前题标记" : "标记当前题"\}/);
  assert.match(workbench, /onClick=\{\(\) => toggleFlag\(activeFlagQuestionIds\)\}/);
  assert.match(workbench, /activeFlagQuestionIds[\s\S]*?sharedQuestionIds/);
  assert.match(workbench, /已标记\$\{label\}。可点击底部“检查标记”返回复查。/);
  assert.match(css, /\.dock-flag-button\.active/);
});

test("marked questions can be reviewed cyclically across parts", () => {
  assert.match(workbench, /const flaggedDockTargets = dockQuestions\.filter/);
  assert.match(workbench, /const reviewNextFlagged = \(\) =>/);
  assert.match(workbench, /\(currentFlaggedIndex \+ 1\) % flaggedDockTargets\.length/);
  assert.match(workbench, /scrollToQuestion\(target\.controlId, Number\(target\.part\.number\)\)/);
  assert.match(workbench, /检查标记题，共 \$\{flaggedCount\} 题/);
  assert.match(workbench, /还有 \$\{flaggedCount\} 道题标记为待检查/);
  assert.match(css, /\.dock-review-button strong/);
});

test("manual drafts retain flags and make their count visible after returning", () => {
  assert.match(workbench, /flagged:\s*Record<string, boolean>/);
  assert.match(workbench, /setFlagged\(draft\?\.flagged \|\| \{\}\)/);
  assert.match(workbench, /restoredFlaggedCount/);
  assert.match(workbench, /function SourceQuestionGroupControl\(\{[\s\S]*?flagged,[\s\S]*?onFlag/);
  assert.match(workbench, /<SourceMatchingMatrix[\s\S]*?flagged=\{flagged\}[\s\S]*?onFlag=\{onFlag\}/);
  assert.match(workbench, /<SourceHtmlQuestionBlock[\s\S]*?flagged=\{flagged\}[\s\S]*?onFlag=\{onFlag\}/);
  assert.match(workbench, /<SourceStructuredQuestionBlock[\s\S]*?flagged=\{flagged\}[\s\S]*?onFlag=\{onFlag\}/);
  assert.match(workbench, /className="source-flag-controls"/);
  assert.match(workbench, /dataset\.flagged = "true"/);
  assert.match(workbench, /source-question-row\$\{marked \? " flagged" : ""\}/);
  assert.match(workbench, /source-matrix-question-heading/);
  assert.doesNotMatch(css, /data-source-visual="true"\]\s+\.question-tools\s+\.flag-button/);
  assert.match(css, /\.source-questions-content input\[data-flagged="true"\]/);
  assert.match(css, /\.source-matching-matrix tbody tr\.flagged th/);
  assert.match(css, /\.source-question-row\.flagged/);
  assert.match(workbench, /已恢复答案、计时和 \$\{restoredFlaggedCount\} 道标记题/);
  assert.match(workbench, /标记 \{Object\.values\(draft\.flagged \|\| \{\}\)\.filter\(Boolean\)\.length\} 题/);
});
