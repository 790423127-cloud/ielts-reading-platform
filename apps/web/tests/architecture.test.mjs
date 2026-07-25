import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const shell = fs.readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const practicePage = fs.readFileSync(new URL("../app/practice/page.tsx", import.meta.url), "utf8");
const workbench = fs.readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const review = fs.readFileSync(new URL("../components/WrongReviewCenter.tsx", import.meta.url), "utf8");
const methods = fs.readFileSync(new URL("../components/MethodLearningCenter.tsx", import.meta.url), "utf8");
const ability = fs.readFileSync(new URL("../components/AbilityTrainingCenter.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("Next.js owns navigation instead of legacy hash routers", () => {
  assert.match(shell, /usePathname/);
  assert.match(shell, /next\/link/);
  assert.match(shell, /\/methods/);
  assert.match(shell, /\/ability/);
  assert.doesNotMatch(layout + shell + workbench + review + methods + ability, /hashchange|popstate|MutationObserver|V311Router|v320-nav-guard/);
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

test("wrong-question center routes to exact method and ability training", () => {
  assert.match(review, /fetchWrongQuestions/);
  assert.match(review, /method_course_id/);
  assert.match(review, /recommended_skill_id/);
  assert.match(review, /连续答对两次/);
});

test("method courses are fixed content without an AI request path", () => {
  assert.match(methods, /fetchMethodCourses/);
  assert.match(methods, /5个基础方法/);
  assert.match(methods, /17种具体题型/);
  assert.match(methods, /AI调用次数为0/);
  assert.doesNotMatch(methods, /chat\/completions|generateCoach|askTeacher|submitAI/i);
});

test("ability training loads verified questions and submits to server", () => {
  assert.match(ability, /fetchAbilitySkills/);
  assert.match(ability, /generateAbilitySet/);
  assert.match(ability, /submitAbilitySet/);
  assert.match(ability, /真实题库/);
  assert.match(api, /\/api\/v1\/ability\/generate/);
  assert.match(api, /\/api\/v1\/ability\/submit/);
  assert.doesNotMatch(ability, /fakeQuestion|generatedQuestion|mockQuestion/i);
});

test("learning and exam surfaces remain text-only", () => {
  assert.doesNotMatch(workbench + review + methods + ability + api, /microphone|MediaRecorder|getUserMedia|speechRecognition|audio\//i);
});
