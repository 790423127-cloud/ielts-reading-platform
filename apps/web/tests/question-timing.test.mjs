import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const ability = readFileSync(new URL("../components/AbilityTrainingCenter.tsx", import.meta.url), "utf8");
const report = readFileSync(new URL("../components/StageReportCenter.tsx", import.meta.url), "utf8");

test("exam and ability sessions record active-question elapsed seconds", () => {
  for (const source of [workbench, ability]) {
    assert.match(source, /questionElapsedSeconds/);
    assert.match(source, /activeQuestionIdRef/);
    assert.match(source, /question_elapsed_seconds/);
  }
  assert.match(workbench, /submittedQuestionTimings/);
  assert.match(workbench, /partElapsedSeconds/);
  assert.match(workbench, /part_elapsed_seconds/);
  assert.match(workbench, /querySelector<HTMLElement>\("\.questions-pane"\)/);
});

test("stage reports show three slow correct and five slow wrong questions", () => {
  assert.match(report, /slowest_correct_questions/);
  assert.match(report, /slowest_wrong_questions/);
  assert.match(report, /回答正确<\/span><strong>最耗时 3 题/);
  assert.match(report, /回答错误<\/span><strong>最耗时 5 题/);
});
