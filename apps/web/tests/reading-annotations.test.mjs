import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("../components/ReadingAnnotationLayer.tsx", import.meta.url), "utf8");
const model = readFileSync(new URL("../lib/readingAnnotations.ts", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/reading-annotations.css", import.meta.url), "utf8");

test("reading annotation layer is mounted without replacing ExamWorkbench", () => {
  assert.match(layout, /<ReadingAnnotationLayer \/>/);
  assert.doesNotMatch(layout, /ExamWorkbench/);
  assert.match(component, /\.passage-copy \.passage-paragraph p/);
});

test("selection toolbar supports highlight, notes and vocabulary capture with full source", () => {
  assert.match(component, />高亮<\/button>/);
  assert.match(component, />笔记<\/button>/);
  assert.match(component, /加入词汇本/);
  assert.match(component, /source_sentence: selection\.sentence/);
  assert.match(component, /test_id: selection\.testId/);
  assert.match(component, /test_title: selection\.testTitle/);
  assert.match(component, /part_number: selection\.partNumber/);
});

test("stable locator stores offsets plus text anchors and migrates old drafts", () => {
  assert.match(model, /locateReadingAnnotation/);
  assert.match(model, /startOffset/);
  assert.match(model, /endOffset/);
  assert.match(model, /prefix/);
  assert.match(model, /suffix/);
  assert.match(model, /migrateLegacyAnnotations/);
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

test("history and mobile selection are restored without changing question layout", () => {
  assert.match(component, /READING_HISTORY_EVENT/);
  assert.match(component, /历史标注/);
  assert.match(component, /selectionchange/);
  assert.match(component, /touchend/);
  assert.match(css, /@media \(max-width: 680px\)/);
  assert.doesNotMatch(css, /\.exam-grid|\.questions-pane|\.question-rail/);
});
