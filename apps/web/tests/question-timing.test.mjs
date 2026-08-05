import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const ability = readFileSync(new URL("../components/AbilityTrainingCenter.tsx", import.meta.url), "utf8");
const report = readFileSync(new URL("../components/StageReportCenter.tsx", import.meta.url), "utf8");
const activity = readFileSync(new URL("../lib/useStudyActivity.ts", import.meta.url), "utf8");

test("exam and ability sessions record active-question elapsed seconds", () => {
  for (const source of [workbench, ability]) {
    assert.match(source, /questionElapsedSeconds/);
    assert.match(source, /activeQuestionIdRef/);
    assert.match(source, /questionElapsedSeconds/);
  }
  assert.match(workbench, /submittedQuestionTimings/);
  assert.match(workbench, /partElapsedSeconds/);
  assert.match(workbench, /partElapsedSeconds/);
  assert.match(workbench, /querySelector<HTMLElement>\("\.questions-pane"\)/);
});

test("study timers count only visible focused recent activity and pause while idle", () => {
  assert.match(activity, /STUDY_IDLE_TIMEOUT_MS = 60_000/);
  assert.match(activity, /document\.visibilityState === "visible"/);
  assert.match(activity, /document\.hasFocus\(\)/);
  assert.match(activity, /"pointerdown",\s*"pointermove",\s*"keydown",\s*"wheel"/);
  assert.match(activity, /document\.addEventListener\("scroll", markStudyActivity/);
  assert.match(activity, /window\.addEventListener\("blur", suspendUntilNextActivity\)/);
  for (const source of [workbench, ability]) {
    assert.match(source, /useStudyActivity/);
    assert.match(source, /if \(!shouldCountStudyTime\(\)\) \{/);
    assert.match(source, /活跃计时/);
    assert.match(source, /静止暂停/);
  }
});

test("stage reports show three slow correct and five slow wrong questions", () => {
  assert.match(report, /slowest_correct_questions/);
  assert.match(report, /slowest_wrong_questions/);
  assert.match(report, /回答正确<\/span><strong>最耗时 3 题/);
  assert.match(report, /回答错误<\/span><strong>最耗时 5 题/);
});
