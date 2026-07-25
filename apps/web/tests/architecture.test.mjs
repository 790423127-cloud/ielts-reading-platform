import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const shell = fs.readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const practicePage = fs.readFileSync(new URL("../app/practice/page.tsx", import.meta.url), "utf8");
const workbench = fs.readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("Next.js owns navigation instead of legacy hash routers", () => {
  assert.match(shell, /usePathname/);
  assert.match(shell, /next\/link/);
  assert.doesNotMatch(layout + shell + workbench, /hashchange|popstate|MutationObserver|V311Router|v320-nav-guard/);
});

test("practice route uses the new server-scored exam workbench", () => {
  assert.match(practicePage, /ExamWorkbench/);
  assert.match(workbench, /fetchPublicTest/);
  assert.match(workbench, /submitSession/);
  assert.match(workbench, /60分钟模拟考试/);
  assert.match(workbench, /localStorage/);
  assert.doesNotMatch(workbench, /dangerouslySetInnerHTML/);
});

test("public question transport type cannot carry answers or explanations", () => {
  const publicQuestionType = api.match(/export type PublicQuestion = \{([\s\S]*?)\n\};/);
  assert.ok(publicQuestionType);
  assert.doesNotMatch(publicQuestionType[1], /answer|evidence|analysis|reason|paraphrasing|keywords/);
  assert.match(api, /\/api\/v1\/question-bank\/tests/);
  assert.match(api, /\/api\/v1\/sessions\/submit/);
});

test("exam workbench remains text-only", () => {
  assert.doesNotMatch(workbench + api, /microphone|MediaRecorder|getUserMedia|speechRecognition|audio\//i);
});
