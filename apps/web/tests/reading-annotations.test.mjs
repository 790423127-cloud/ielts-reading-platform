import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("../components/ReadingAnnotationLayer.tsx", import.meta.url), "utf8");
const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/reading-annotations.css", import.meta.url), "utf8");

test("reading annotation layer is mounted without replacing ExamWorkbench", () => {
  assert.match(layout, /<ReadingAnnotationLayer \/>/);
  assert.doesNotMatch(layout, /ExamWorkbench/);
  assert.match(component, /\.passage-copy \.passage-paragraph p/);
});

test("selection toolbar supports highlight, notes and vocabulary capture", () => {
  assert.match(component, />高亮<\/button>/);
  assert.match(component, />笔记<\/button>/);
  assert.match(component, /加入词汇本/);
  assert.match(component, /captureVocabulary\(\{/);
  assert.match(component, /source_sentence: selection\.sentence/);
  assert.match(component, /test_title: selection\.testTitle/);
  assert.match(component, /part_number: selection\.partNumber/);
});

test("annotations persist locally with stable text offsets and context", () => {
  assert.match(component, /ielts-platform-reading-annotations:/);
  assert.match(component, /startOffset/);
  assert.match(component, /endOffset/);
  assert.match(component, /prefix/);
  assert.match(component, /suffix/);
  assert.match(component, /window\.localStorage\.setItem/);
});

test("mobile toolbar remains reachable without changing question layout", () => {
  assert.match(css, /@media \(max-width: 680px\)/);
  assert.match(css, /\.reading-selection-toolbar/);
  assert.doesNotMatch(css, /\.exam-grid|\.questions-pane|\.question-rail/);
});
