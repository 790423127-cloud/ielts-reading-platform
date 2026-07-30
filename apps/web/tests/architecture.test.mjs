import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const layout = fs.readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const dashboard = fs.readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const shell = fs.readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const practicePage = fs.readFileSync(new URL("../app/practice/page.tsx", import.meta.url), "utf8");
const workbench = fs.readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const review = fs.readFileSync(new URL("../components/WrongReviewCenter.tsx", import.meta.url), "utf8");
const methods = fs.readFileSync(new URL("../components/MethodLearningCenter.tsx", import.meta.url), "utf8");
const ability = fs.readFileSync(new URL("../components/AbilityTrainingCenter.tsx", import.meta.url), "utf8");
const reports = fs.readFileSync(new URL("../components/StageReportCenter.tsx", import.meta.url), "utf8");
const api = fs.readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const webPackage = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url), "utf8"));
const apiProject = fs.readFileSync(new URL("../../../services/api/pyproject.toml", import.meta.url), "utf8");
const apiConfig = fs.readFileSync(new URL("../../../services/api/app/core/config.py", import.meta.url), "utf8");
const readme = fs.readFileSync(new URL("../../../README.md", import.meta.url), "utf8");
const migration = fs.readFileSync(new URL("../../../docs/MIGRATION.md", import.meta.url), "utf8");

test("release surfaces agree on version and replacement-validation status", () => {
  assert.equal(webPackage.version, "0.5.0");
  assert.match(dashboard, /CURRENT_VERSION = "0\.5\.0"/);
  assert.match(dashboard, /旧版替代仍在验收/);
  assert.match(apiProject, /version = "0\.5\.0"/);
  assert.match(apiConfig, /app_version: str = "0\.5\.0"/);
  assert.match(apiConfig, /migration_phase: str = "replacement_validation"/);
  assert.match(readme, /当前发布状态/);
  assert.match(migration, /Phase 6 — replacement validation/);
});

test("Next.js owns navigation instead of legacy hash routers", () => {
  assert.match(shell, /usePathname/);
  assert.match(shell, /next\/link/);
  assert.match(shell, /\/methods/);
  assert.match(shell, /\/ability/);
  assert.match(shell, /方法课程/);
  assert.match(shell, /专项训练/);
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
  assert.match(review, /source_question_ref/);
  assert.match(review, /返回原题重做/);
  assert.match(review, /source_part_number/);
  assert.match(review, /连续答对两次/);
});

test("personal vocabulary book remains part of the reading learning loop", () => {
  assert.match(shell, /href: "\/vocabulary"/);
  assert.match(shell, /label: "生词本"/);
});

test("method courses are fixed content without an AI request path", () => {
  assert.match(methods, /fetchMethodCourses/);
  assert.match(methods, /5个基础方法/);
  assert.match(methods, /17种具体题型/);
  assert.match(methods, /AI调用次数为0/);
  assert.match(methods, /练习这个题型/);
  assert.match(ability, /不重复展示方法课程/);
  assert.doesNotMatch(api, /fetchAbilitySkills/);
  assert.doesNotMatch(methods, /chat\/completions|generateCoach|askTeacher|submitAI/i);
});

test("ability training loads verified questions and submits to server", () => {
  assert.match(ability, /fetchTrainingCatalog/);
  assert.match(ability, /generateAbilitySet/);
  assert.match(ability, /submitAbilitySet/);
  assert.match(ability, /17种题型专项/);
  assert.match(ability, /questionRefs/);
  assert.match(ability, /available_questions === 0/);
  assert.match(ability, /暂无可用真题/);
  assert.match(ability, /真实题库/);
  assert.match(api, /\/api\/v1\/ability\/generate/);
  assert.match(api, /\/api\/v1\/ability\/submit/);
  assert.doesNotMatch(ability, /fakeQuestion|generatedQuestion|mockQuestion/i);
});

test("stage report reuses persisted sessions without AI or a duplicate score store", () => {
  assert.match(shell, /\/reports/);
  assert.match(reports, /fetchStageReport/);
  assert.match(reports, /首次练习与相同配置重做分开标记/);
  assert.match(reports, /下载正式 PDF/);
  assert.match(reports, /下载 DOCX/);
  assert.match(reports, />打印<\/button>/);
  assert.match(api, /\/api\/v1\/reports\/stage/);
  assert.doesNotMatch(reports, /chat\/completions|askTeacher|generateCoach/i);
});

test("unsubmitted ability answers are never described as saved", () => {
  assert.match(ability, /放弃本组并返回/);
  assert.match(ability, /当前答案尚未提交，返回后不会保存/);
  assert.match(ability, /window\.confirm/);
  assert.doesNotMatch(ability, /保存记录并返回/);
});

test("learning and exam surfaces remain text-only", () => {
  assert.doesNotMatch(workbench + review + methods + ability + api, /microphone|MediaRecorder|getUserMedia|speechRecognition|audio\//i);
});
