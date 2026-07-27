import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("shared multi-select groups synchronize every deterministic score slot", () => {
  const workbench = fs.readFileSync(path.join(root, "components", "ExamWorkbench.tsx"), "utf8");
  const apiTypes = fs.readFileSync(path.join(root, "lib", "api.ts"), "utf8");
  const styles = fs.readFileSync(path.join(root, "app", "globals.css"), "utf8");

  assert.match(apiTypes, /shared_response\?: boolean/);
  assert.match(apiTypes, /shared_response_question_ids\?: string\[\]/);
  assert.match(workbench, /function sharedQuestionIds/);
  assert.match(workbench, /for \(const questionId of ids\) next\[questionId\] = value/);
  assert.match(workbench, /group\.shared_response \? group\.questions\.slice\(0, 1\)/);
  assert.match(workbench, /group\.shared_response \? sharedQuestionIds\(group\)\.length : 1/);
  assert.match(workbench, /current\.length < \(requiredChoices \|\| 2\)/);
  assert.match(workbench, /function answerIsComplete/);
  assert.match(workbench, /value\.length >= requiredChoices/);
  assert.match(workbench, /\$\{numbers\[0\]\}–\$\{numbers\[numbers\.length - 1\]\}/);
  assert.match(styles, /\.question-title-row \{[^}]*grid-template-columns: max-content minmax\(0, 1fr\) auto/);
});

test("navigation inventory reads the actually available backend question bank", () => {
  const shell = fs.readFileSync(path.join(root, "components", "AppShell.tsx"), "utf8");
  const workbench = fs.readFileSync(path.join(root, "components", "ExamWorkbench.tsx"), "utf8");
  const ability = fs.readFileSync(path.join(root, "components", "AbilityTrainingCenter.tsx"), "utf8");

  assert.match(shell, /fetchTests/);
  assert.match(shell, /libraryStats/);
  assert.match(shell, /tests\.reduce/);
  assert.match(shell, /题库可用/);
  assert.doesNotMatch(shell, /58套题库已迁移/);
  assert.match(workbench, /tests\.length/);
  assert.match(ability, /available_questions/);
});
