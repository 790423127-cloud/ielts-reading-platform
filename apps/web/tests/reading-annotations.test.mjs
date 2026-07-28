import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("../components/ReadingAnnotationLayer.tsx", import.meta.url), "utf8");
const workbench = readFileSync(new URL("../components/ExamWorkbench.tsx", import.meta.url), "utf8");
const model = readFileSync(new URL("../lib/readingAnnotations.ts", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/reading-annotations.css", import.meta.url), "utf8");

test("reading annotation layer is mounted without replacing ExamWorkbench", () => {
  assert.match(layout, /<ReadingAnnotationLayer \/>/);
  assert.doesNotMatch(layout, /ExamWorkbench/);
  assert.match(component, /\.passage-copy \.passage-unit/);
  assert.match(component, /\.questions-pane \.question-annotation-unit/);
  assert.match(workbench, /data-test-id=\{test\.id\}/);
  assert.match(component, /workbench\.dataset\.partNumber/);
  assert.match(component, /\.dock-section\.active \.dock-section-label, \.dock-part-tabs button\.active/);
});

test("question instructions, prompts and options share the reading annotation layer", () => {
  assert.match(workbench, /question-instructions question-annotation-unit/);
  assert.match(workbench, /questions-pane-heading question-annotation-unit/);
  assert.match(workbench, /answer-option-copy question-annotation-unit/);
  assert.match(component, /sourceKind: paragraph\.matches\("\.question-annotation-unit"\)/);
  assert.match(css, /\.questions-pane \.question-annotation-unit/);
});

test("selection toolbar supports highlight, notes and vocabulary capture with full source", () => {
  assert.match(component, /selectedAnnotation\?\.kind === "highlight"/);
  assert.match(component, /persist\(annotations\.filter\(\(item\) => item\.id !== selectedAnnotation\.id\)\)/);
  assert.match(component, /\? "取消高亮" : "高亮"/);
  assert.match(component, />笔记<\/button>/);
  assert.match(component, /加入生词本/);
  assert.match(component, /source_sentence: selection\.sentence/);
  assert.match(component, /test_id: selection\.testId/);
  assert.match(component, /test_title: selection\.testTitle/);
  assert.match(component, /part_number: selection\.partNumber/);
});

test("an existing CSS highlight can be clicked directly and cleared", () => {
  assert.match(component, /function highlightedSelectionAtPoint/);
  assert.match(component, /range\.getClientRects\(\)/);
  assert.match(component, /annotation\.kind !== "highlight"/);
  assert.match(component, /highlightedSelectionAtPoint\(point\.x, point\.y/);
  assert.match(component, /selectionchange", scheduleSelectionCapture/);
  assert.match(component, /if \(!window\.getSelection\(\)\?\.isCollapsed\) scheduleCapture\(\)/);
  assert.match(component, /selection\.rect\.bottom \+ 9/);
});

test("stable locator stores offsets plus text anchors and migrates old drafts", () => {
  assert.match(model, /locateReadingAnnotation/);
  assert.match(model, /startOffset/);
  assert.match(model, /endOffset/);
  assert.match(model, /prefix/);
  assert.match(model, /suffix/);
  assert.match(model, /migrateLegacyAnnotations/);
  assert.match(model, /legacyAnnotation/);
  assert.match(model, /normalizeWithRawIndexes/);
});

test("annotations join local exam drafts and submitted Session payloads", () => {
  assert.match(model, /ielts-platform-draft:/);
  assert.match(model, /syncAnnotationsIntoExamDrafts/);
  assert.match(api, /readAnnotationsForSubmission/);
  assert.match(api, /JSON\.stringify\(\{ \.\.\.payload, annotations \}\)/);
  assert.match(api, /cacheSessionAnnotations/);
  assert.match(api, /annotations\?: ReadingAnnotation\[\]/);
});

test("annotation synchronization is event-driven instead of polling localStorage", () => {
  assert.match(component, /const restored = readReadingAnnotationDraft/);
  assert.match(component, /syncAnnotationsIntoExamDrafts\(context\.testId, restored\)/);
  assert.match(model, /writeReadingAnnotationDraft[\s\S]*syncAnnotationsIntoExamDrafts\(testId, clean\)/);
  assert.doesNotMatch(component, /setInterval/);
  assert.doesNotMatch(component, /900/);
});

test("history and mobile selection are restored without changing question layout", () => {
  assert.match(component, /READING_HISTORY_EVENT/);
  assert.match(component, /历史标注/);
  assert.match(component, /selectionchange/);
  assert.match(component, /touchend/);
  assert.match(css, /@media \(max-width: 680px\)/);
  assert.doesNotMatch(css, /\.exam-grid|\.question-rail/);
});
