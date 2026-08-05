import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const support = readFileSync(new URL("../components/SupportCenter.tsx", import.meta.url), "utf8");

test("starting from a test card creates a fresh attempt instead of silently restoring answers", () => {
  assert.match(workbench, /async function startExam\([\s\S]*?resumeDraft = false,[\s\S]*?selectedDraft: DraftState \| null = null/);
  assert.match(workbench, /if \(resumeDraft\) \{[\s\S]*?window\.localStorage\.getItem\(key\)[\s\S]*?\} else \{\s*window\.localStorage\.removeItem\(key\);/);
  assert.match(workbench, /setAnswers\(draft\?\.answers \|\| \{\}\)/);
  assert.match(workbench, /const nextSubmissionId = draft\?\.clientSubmissionId \|\| newSubmissionId\(\)/);
  assert.match(workbench, /setClientSubmissionId\(nextSubmissionId\)/);
  assert.match(workbench, /beginReadingAttempt\(\{[\s\S]*attemptId: nextSubmissionId,[\s\S]*annotations: draft\?\.annotations \|\| \[\]/);
  assert.match(workbench, /onClick=\{\(\) => void startExam\(item\.id, "study", \[\]\)\}/);
  assert.match(workbench, /onClick=\{\(\) => void startExam\(item\.id, "part_practice", \[part\]\)\}/);
});

test("draft restoration is explicit and remains available from the draft manager", () => {
  assert.match(workbench, /继续草稿/);
  assert.match(workbench, /draft = selectedDraft/);
  assert.match(workbench, /onClick=\{\(\) => \{\s*setShowDrafts\(true\);\s*refreshDrafts\(\);/);
  assert.match(workbench, /startExam\(draft\.testId, draft\.mode \|\| "study", draft\.partNumbers \|\| \[\], true, draft\)/);
  assert.match(workbench, /已从草稿管理器继续上次未完成的答案和计时/);
  assert.match(support, /普通退出或从题卡再次开始均为空白练习/);
  assert.match(support, /只有从“管理草稿”点击继续/);
});

test("local recovery drafts are created only by an explicit manual save", () => {
  assert.match(workbench, /const draftSnapshotRef = useRef<DraftState \| null>\(null\)/);
  assert.match(workbench, /const hasDraftProgress = answeredCount > 0 \|\| Object\.values\(flagged\)\.some\(Boolean\) \|\| annotationCount > 0/);
  assert.match(workbench, /const hasAnswers = Object\.values\(draft\.answers\)\.some\(answerIsPresent\)/);
  assert.match(workbench, /const hasAnnotations = Boolean\(draft\.annotations\?\.length\)/);
  assert.match(workbench, /if \(!hasAnswers && !hasFlags && !hasAnnotations\) return null/);
  assert.match(workbench, /annotations: test \? readAnnotationsForSubmission\(test\.id, partNumbers\) : \[\]/);
  assert.match(workbench, /function saveDraftManually\(\): boolean/);
  assert.match(workbench, /onClick=\{saveDraftManually\}>保存草稿/);
  assert.match(workbench, /setDrafts\(\(current\) => \[summary, \.\.\.current\.filter/);
  assert.match(workbench, /当前答案不会自动保存/);
  assert.doesNotMatch(workbench, /setInterval\(persistCurrentDraft/);
  assert.doesNotMatch(workbench, /beforeunload/);
});

test("empty automatic drafts are hidden instead of filling the draft manager", () => {
  assert.match(workbench, /const hasAnswers = Object\.values\(value\.answers \|\| \{\}\)\.some\(answerIsPresent\)/);
  assert.match(workbench, /const hasAnnotations = Array\.isArray\(value\.annotations\) && value\.annotations\.length > 0/);
  assert.match(workbench, /if \(!hasAnswers && !hasFlags && !hasAnnotations\) continue/);
});
