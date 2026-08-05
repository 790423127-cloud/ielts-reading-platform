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
  assert.match(component, /"取消二次高亮"/);
  assert.match(component, /selectionOverlapsPrimaryHighlight[\s\S]*\? "二次高亮"[\s\S]*: "高亮"/);
  assert.match(component, />\s*笔记\s*<\/button>/);
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

test("a selection inside the primary highlight creates the reference app's pink second highlight", () => {
  assert.match(model, /highlightLevel\?: "primary" \| "secondary"/);
  assert.match(component, /SECONDARY_HIGHLIGHT_NAME/);
  assert.match(component, /selectionOverlapsPrimaryHighlight \? "secondary" : "primary"/);
  assert.match(component, /已添加二次高亮/);
  assert.match(css, /::highlight\(reading-highlight-secondary\)/);
});

test("stable locator stores offsets plus text anchors", () => {
  assert.match(model, /locateReadingAnnotation/);
  assert.match(model, /startOffset/);
  assert.match(model, /endOffset/);
  assert.match(model, /prefix/);
  assert.match(model, /suffix/);
  assert.match(model, /normalizeWithRawIndexes/);
});

test("annotations stay inside the active attempt and join only explicit drafts or submissions", () => {
  assert.match(model, /let activeReadingAttempt: ReadingAttemptDetail \| null = null/);
  assert.match(model, /export function beginReadingAttempt/);
  assert.match(model, /export function updateReadingAttemptAnnotations/);
  assert.match(component, /updateReadingAttemptAnnotations\(context\.testId, next\)/);
  assert.match(workbench, /annotations\?: ReadingAnnotation\[\]/);
  assert.match(workbench, /annotations: test \? readAnnotationsForSubmission\(test\.id, partNumbers\) : \[\]/);
  assert.match(workbench, /annotations: draft\?\.annotations \|\| \[\]/);
  assert.match(api, /readAnnotationsForSubmission/);
  assert.match(api, /JSON\.stringify\(\{ \.\.\.payload, annotations \}\)/);
  assert.match(api, /cacheSessionAnnotations/);
  assert.match(api, /annotations\?: ReadingAnnotation\[\]/);
  assert.doesNotMatch(model, /localStorage/);
  assert.doesNotMatch(model, /ielts-platform-reading-draft:/);
});

test("fresh and resumed annotation state is event-driven instead of browser auto-save", () => {
  assert.match(component, /READING_ATTEMPT_EVENT/);
  assert.match(component, /READING_ANNOTATIONS_EVENT/);
  assert.match(model, /emitReadingEvent\(READING_ATTEMPT_EVENT, activeReadingAttempt\)/);
  assert.match(model, /emitReadingEvent\(READING_ANNOTATIONS_EVENT, activeReadingAttempt\)/);
  assert.match(workbench, /beginReadingAttempt\(\{[\s\S]*annotations: draft\?\.annotations \|\| \[\]/);
  assert.doesNotMatch(component, /setInterval/);
  assert.doesNotMatch(component, /writeReadingAnnotationDraft/);
  assert.doesNotMatch(component, /syncAnnotationsIntoExamDrafts/);
});

test("history and mobile selection are restored without changing question layout", () => {
  assert.match(component, /READING_HISTORY_EVENT/);
  assert.match(component, /历史标注/);
  assert.match(component, /setHistory\(\{ \.\.\.detail, annotations: sanitizeReadingAnnotations\(detail\.annotations\) \}\);[\s\S]*setPanelOpen\(false\)/);
  assert.match(component, /selectionchange/);
  assert.match(component, /touchend/);
  assert.match(css, /@media \(max-width: 680px\)/);
  assert.doesNotMatch(css, /\.exam-grid|\.question-rail/);
});

test("optional browser storage cannot make a verified public test request fail", () => {
  assert.match(
    model,
    /export function rememberCurrentReadingTest[\s\S]*try \{[\s\S]*sessionStorage\.setItem[\s\S]*\} catch \{/
  );
  assert.match(api, /const test = await apiJson<PublicTest>[\s\S]*rememberCurrentReadingTest[\s\S]*return test/);
});

test("source HTML passages and answer choices keep stable selectable annotation anchors", () => {
  assert.match(component, /\.passage-copy\.passage-unit/);
  assert.match(workbench, /className="passage-copy passage-source-html passage-unit"/);
  assert.match(workbench, /const StableHtmlDiv = memo/);
  assert.match(workbench, /className="source-questions-content question-annotation-unit"/);
  assert.match(workbench, /className="question-annotation-unit" html=\{option\.content_html \|\| ""\}/);
  assert.match(css, /\.passage-copy\.passage-unit/);
});

test("selecting answer text does not toggle answers or start matching-card dragging", () => {
  assert.match(workbench, /function preventAnswerToggleForSelection/);
  assert.match(workbench, /onClickCapture=\{preventAnswerToggleForSelection\}/);
  assert.match(workbench, /function prepareMatchingTextSelection/);
  assert.match(workbench, /onPointerDown=\{prepareMatchingTextSelection\}/);
  assert.match(css, /\.questions-pane \.question-annotation-unit/);
});

test("slow pointer selection is captured only after the pointer is released", () => {
  assert.match(component, /let pointerSelectionActive = false/);
  assert.match(component, /pointerSelectionActive = true/);
  assert.match(component, /if \(pointerSelectionActive\) return/);
  assert.match(component, /addEventListener\("pointerdown", beginPointerSelection, true\)/);
  assert.match(component, /addEventListener\("pointerup", schedulePointerCapture, true\)/);
  assert.match(component, /removeEventListener\("pointerdown", beginPointerSelection, true\)/);
  assert.match(component, /removeEventListener\("pointerup", schedulePointerCapture, true\)/);
});
