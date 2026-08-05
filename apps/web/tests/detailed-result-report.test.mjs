import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const history = readFileSync(new URL("../components/HistoryCenter.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");

test("submitted results stay compact and open one IELTSBro-style question analysis at a time", () => {
  assert.match(workbench, /const showDetailedReview = historyEntrySource/);
  assert.match(workbench, /showDetailedReview \? <>[\s\S]*?result-performance-section/);
  assert.doesNotMatch(workbench, /result-review-section/);
  assert.doesNotMatch(workbench, /result-source-analysis-actions/);
  assert.match(workbench, /function QuestionAnalysisLink/);
  assert.match(workbench, /className="question-analysis-link"/);
  assert.match(workbench, /onOpenAnalysis=\{setSelectedReviewQuestion\}/);
  assert.match(workbench, /<InlineQuestionReview question=\{reviewResult\} \/>/);
  assert.match(workbench, /control\.insertAdjacentElement\("afterend", link\)/);
  assert.match(css, /\.question-analysis-link/);
  assert.match(css, /fieldset \.question-analysis-link \{ pointer-events: auto; \}/);
  assert.match(workbench, /setSelectedReviewQuestion\(question\)/);
  assert.match(workbench, /ResultQuestionAnalysisDialog/);
  assert.match(workbench, /你的答案/);
  assert.match(workbench, /正确答案/);
  assert.match(workbench, /question\.user_answer \|\| "未作答"/);
  assert.match(workbench, /前往练习记录/);
});

test("historical reports reload the public passage without exposing answer keys before submission", () => {
  assert.match(history, /\/practice\?session=/);
  assert.match(history, />详细报告</);
  assert.match(workbench, /new URLSearchParams\(window\.location\.search\)\.get\("session"\)/);
  assert.match(workbench, /historyEntrySource \? "返回练习记录" : "返回题库"/);
  assert.match(workbench, /sourceTest = await fetchPublicTest\(session\.result\.test_id\)/);
  assert.match(workbench, /原文与我的作答记录/);
  assert.match(workbench, /<ResultPassageDisplay[\s\S]*?part=\{activeReviewPart\}/);
  assert.match(workbench, /result-source-split/);
  assert.match(workbench, /<fieldset disabled>/);
  assert.match(workbench, /<QuestionGroupControl[\s\S]*?answers=\{activeHistoricalAnswers\}/);
  assert.match(workbench, /按原做题界面只读还原/);
  assert.match(workbench, /exam-question-dock result-source-part-dock/);
  assert.match(workbench, /dock-section-strip/);
  assert.match(workbench, /dock-section-label result-source-dock-label/);
  assert.match(workbench, /dock-question-list result-source-dock-questions/);
  assert.doesNotMatch(workbench, /<details className="result-source-part"/);
  assert.doesNotMatch(api.match(/export type PublicQuestion = \{[\s\S]*?\n\};/)?.[0] || "", /correct_answer|analysis|evidence/);
});

test("wrong answers are shown inside their original answer controls instead of a duplicate list", () => {
  assert.match(workbench, /reviewResults=\{activeReviewQuestionResults\}/);
  assert.match(workbench, /function InlineAnswerReview/);
  assert.match(workbench, /answerReviewClass\(option\.code, \[reviewResult\]\)/);
  assert.match(workbench, /question-inline-review-list/);
  assert.doesNotMatch(workbench, /className="result-source-answer-key"/);
});

test("matching matrix report marks the correct answer with a green radio dot", () => {
  assert.match(css, /\.matching-answer-matrix td\.review-correct-option \.matrix-answer-radio > span:not\(\.sr-only\)::after/);
  assert.match(css, /background: #14966f/);
});

test("the single-question dialog uses server scoring evidence and embeds the existing AI teacher", () => {
  for (const field of [
    "type_results",
    "question_results",
    "wrong_reasons",
    "evidence"
  ]) {
    assert.match(workbench, new RegExp(field));
  }
  assert.match(workbench, /题型表现/);
  assert.match(workbench, /result-answer-sentence-label/);
  assert.match(workbench, /原文答案句/);
  assert.match(workbench, /showPassageTranslations/);
  assert.match(workbench, /result-passage-translation/);
  assert.match(workbench, />\s*翻译<i aria-hidden="true" \/>/);
  assert.match(workbench, /<AiTeacherPanel/);
  assert.match(workbench, /contextType="wrong_question"/);
  assert.match(workbench, /我的高亮与笔记/);
});

test("translation covers br-only source HTML and always renders unmatched paragraphs", () => {
  assert.match(workbench, /document\.createTreeWalker\(root, NodeFilter\.SHOW_TEXT/);
  assert.match(workbench, /const textCandidates: Text\[\] = \[\]/);
  assert.match(workbench, /unmatchedTranslations\.push\(translation\)/);
  assert.match(workbench, /result-passage-translation-fallback/);
  assert.match(workbench, /heading\.textContent = inserted \? "其余段落翻译" : "本 Part 中文翻译"/);
  assert.match(workbench, /root\.prepend\(fallback\)/);
  assert.match(css, /\.result-passage-translation-fallback/);
});

test("saved highlights stay collapsed until the learner explicitly opens them", () => {
  assert.match(workbench, /const \[resultAnnotationsOpen, setResultAnnotationsOpen\] = useState\(false\)/);
  assert.match(workbench, /setResultAnnotationsOpen\(false\)/);
  assert.match(workbench, /aria-expanded=\{resultAnnotationsOpen\}/);
  assert.match(workbench, /resultAnnotationsOpen \? \(/);
  assert.match(workbench, /setResultAnnotationsOpen\(\(open\) => !open\)/);
  assert.match(workbench, /onClick=\{\(\) => setResultAnnotationsOpen\(true\)\}>高亮与笔记/);
});
