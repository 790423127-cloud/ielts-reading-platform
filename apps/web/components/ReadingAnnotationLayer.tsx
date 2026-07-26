"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { captureVocabulary } from "@/lib/learningApi";
import {
  currentReadingTest,
  locateReadingAnnotation,
  normalizeReadingText,
  readReadingAnnotationDraft,
  READING_HISTORY_EVENT,
  sanitizeReadingAnnotations,
  syncAnnotationsIntoExamDrafts,
  writeReadingAnnotationDraft,
  type AnnotationKind,
  type ReadingAnnotation,
  type ReadingHistoryDetail
} from "@/lib/readingAnnotations";

type ReadingContext = {
  testId: string;
  testTitle: string;
  partNumber: number;
};

type PendingSelection = ReadingContext & {
  rect: DOMRect;
  paragraphIndex: number;
  paragraphText: string;
  startOffset: number;
  endOffset: number;
  selectedText: string;
  sentence: string;
};

type HighlightRegistry = {
  set(name: string, value: unknown): void;
  delete(name: string): void;
};

type HighlightConstructor = new (...ranges: Range[]) => unknown;

const HIGHLIGHT_NAME = "reading-highlight";
const NOTE_NAME = "reading-note";

function annotationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function currentContext(): ReadingContext | null {
  const workbench = document.querySelector<HTMLElement>(".exam-workbench");
  if (!workbench) return null;
  const testTitle = normalizeReadingText(
    workbench.querySelector<HTMLElement>(".exam-topbar > div:first-child strong")?.textContent || ""
  );
  const activePartText = workbench.querySelector<HTMLElement>(".exam-part-tabs button.active")?.textContent || "";
  const partMatch = activePartText.match(/(\d+)/);
  const test = currentReadingTest(testTitle);
  if (!test || !partMatch) return null;
  return { testId: test.id, testTitle: test.title, partNumber: Number(partMatch[1]) };
}

function sentenceAround(text: string, start: number, end: number): string {
  const left = text.slice(0, start);
  const right = text.slice(end);
  const leftBoundary = Math.max(
    left.lastIndexOf("."), left.lastIndexOf("!"), left.lastIndexOf("?"),
    left.lastIndexOf("。"), left.lastIndexOf("！"), left.lastIndexOf("？")
  );
  const candidates = [
    right.indexOf("."), right.indexOf("!"), right.indexOf("?"),
    right.indexOf("。"), right.indexOf("！"), right.indexOf("？")
  ].filter((value) => value >= 0);
  const rightBoundary = candidates.length ? Math.min(...candidates) + end + 1 : text.length;
  return normalizeReadingText(text.slice(leftBoundary + 1, rightBoundary)) || normalizeReadingText(text);
}

function textOffset(paragraph: HTMLElement, node: Node, offset: number): number {
  const range = document.createRange();
  range.selectNodeContents(paragraph);
  range.setEnd(node, offset);
  return range.toString().length;
}

function rangeFromOffsets(paragraph: HTMLElement, start: number, end: number): Range | null {
  const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
  let position = 0;
  let startNode: Text | null = null;
  let endNode: Text | null = null;
  let startOffset = 0;
  let endOffset = 0;
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const next = position + node.data.length;
    if (!startNode && start >= position && start <= next) {
      startNode = node;
      startOffset = start - position;
    }
    if (end >= position && end <= next) {
      endNode = node;
      endOffset = end - position;
      break;
    }
    position = next;
  }
  if (!startNode || !endNode) return null;
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  return range;
}

function rangeForAnnotation(paragraph: HTMLElement, annotation: ReadingAnnotation): Range | null {
  const located = locateReadingAnnotation(paragraph.textContent || "", annotation);
  if (!located) return null;
  return rangeFromOffsets(paragraph, located.startOffset, located.endOffset);
}

function highlightApi(): { registry: HighlightRegistry; Highlight: HighlightConstructor } | null {
  const css = CSS as unknown as { highlights?: HighlightRegistry };
  const Highlight = (window as unknown as { Highlight?: HighlightConstructor }).Highlight;
  return css?.highlights && Highlight ? { registry: css.highlights, Highlight } : null;
}

function HighlightedSentence({ annotation }: { annotation: ReadingAnnotation }) {
  const sentence = annotation.sentence || annotation.selectedText;
  const index = sentence.toLocaleLowerCase().indexOf(annotation.selectedText.toLocaleLowerCase());
  if (index < 0) return <small>{sentence}</small>;
  return (
    <small>
      {sentence.slice(0, index)}
      <mark className={annotation.kind === "note" ? "note" : "highlight"}>
        {sentence.slice(index, index + annotation.selectedText.length)}
      </mark>
      {sentence.slice(index + annotation.selectedText.length)}
    </small>
  );
}

export default function ReadingAnnotationLayer() {
  const [mounted, setMounted] = useState(false);
  const [context, setContext] = useState<ReadingContext | null>(null);
  const [annotations, setAnnotations] = useState<ReadingAnnotation[]>([]);
  const [history, setHistory] = useState<ReadingHistoryDetail | null>(null);
  const [selection, setSelection] = useState<PendingSelection | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [savingVocabulary, setSavingVocabulary] = useState(false);
  const selectionTimer = useRef<number | null>(null);

  useEffect(() => setMounted(true), []);

  const refreshContext = useCallback(() => {
    const next = currentContext();
    setContext((current) => {
      if (current?.testId === next?.testId && current?.partNumber === next?.partNumber) return current;
      return next;
    });
  }, []);

  useEffect(() => {
    refreshContext();
    const refreshLater = () => window.setTimeout(refreshContext, 40);
    document.addEventListener("click", refreshLater, true);
    return () => document.removeEventListener("click", refreshLater, true);
  }, [refreshContext]);

  useEffect(() => {
    function onHistory(event: Event) {
      const detail = (event as CustomEvent<ReadingHistoryDetail>).detail;
      if (!detail) return;
      setHistory({ ...detail, annotations: sanitizeReadingAnnotations(detail.annotations) });
      setPanelOpen(Boolean(detail.annotations.length));
    }
    window.addEventListener(READING_HISTORY_EVENT, onHistory);
    return () => window.removeEventListener(READING_HISTORY_EVENT, onHistory);
  }, []);

  useEffect(() => {
    if (!context) {
      setAnnotations([]);
      setSelection(null);
      setNoteOpen(false);
      return;
    }
    setHistory(null);
    setAnnotations(readReadingAnnotationDraft(context.testId, context.testTitle));
    setSelection(null);
    setNoteOpen(false);
    setPanelOpen(false);
  }, [context]);

  useEffect(() => {
    if (!context) return;
    const timer = window.setInterval(() => {
      syncAnnotationsIntoExamDrafts(context.testId, annotations);
    }, 900);
    return () => window.clearInterval(timer);
  }, [annotations, context]);

  const visibleAnnotations = useMemo(
    () => context ? annotations.filter((item) => item.partNumber === context.partNumber) : history?.annotations || [],
    [annotations, context, history]
  );

  const applyHighlights = useCallback(() => {
    const api = highlightApi();
    if (!api) return;
    api.registry.delete(HIGHLIGHT_NAME);
    api.registry.delete(NOTE_NAME);
    if (!context) return;
    const paragraphs = [...document.querySelectorAll<HTMLElement>(".passage-copy .passage-paragraph p")];
    const highlightRanges: Range[] = [];
    const noteRanges: Range[] = [];
    for (const annotation of visibleAnnotations) {
      const paragraph = paragraphs[annotation.paragraphIndex];
      if (!paragraph) continue;
      const range = rangeForAnnotation(paragraph, annotation);
      if (!range) continue;
      if (annotation.kind === "note") noteRanges.push(range);
      else highlightRanges.push(range);
    }
    if (highlightRanges.length) api.registry.set(HIGHLIGHT_NAME, new api.Highlight(...highlightRanges));
    if (noteRanges.length) api.registry.set(NOTE_NAME, new api.Highlight(...noteRanges));
  }, [context, visibleAnnotations]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(applyHighlights);
    const delayed = window.setTimeout(applyHighlights, 100);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(delayed);
    };
  }, [applyHighlights]);

  useEffect(() => {
    function captureSelection() {
      if (!currentContext()) return;
      const browserSelection = window.getSelection();
      if (!browserSelection || browserSelection.isCollapsed || browserSelection.rangeCount !== 1) {
        setSelection(null);
        return;
      }
      const range = browserSelection.getRangeAt(0);
      const startElement = range.startContainer.nodeType === Node.TEXT_NODE
        ? range.startContainer.parentElement
        : range.startContainer as HTMLElement;
      const endElement = range.endContainer.nodeType === Node.TEXT_NODE
        ? range.endContainer.parentElement
        : range.endContainer as HTMLElement;
      const paragraph = startElement?.closest<HTMLElement>(".passage-copy .passage-paragraph p");
      if (!paragraph || !endElement || paragraph !== endElement.closest(".passage-copy .passage-paragraph p")) {
        setSelection(null);
        return;
      }
      const nextContext = currentContext();
      if (!nextContext) return;
      const paragraphs = [...document.querySelectorAll<HTMLElement>(".passage-copy .passage-paragraph p")];
      const paragraphIndex = paragraphs.indexOf(paragraph);
      if (paragraphIndex < 0) return;
      const selectedText = normalizeReadingText(range.toString());
      if (!selectedText || selectedText.length > 300) {
        setSelection(null);
        return;
      }
      const startOffset = textOffset(paragraph, range.startContainer, range.startOffset);
      const endOffset = textOffset(paragraph, range.endContainer, range.endOffset);
      const paragraphText = paragraph.textContent || "";
      const rects = range.getClientRects();
      const rect = rects.length ? rects[rects.length - 1] : range.getBoundingClientRect();
      setSelection({
        ...nextContext,
        rect,
        paragraphIndex,
        paragraphText,
        startOffset,
        endOffset,
        selectedText,
        sentence: sentenceAround(paragraphText, startOffset, endOffset)
      });
      setNoteOpen(false);
      setNoteDraft("");
      setStatus("");
    }

    function scheduleCapture() {
      if (selectionTimer.current != null) window.clearTimeout(selectionTimer.current);
      selectionTimer.current = window.setTimeout(captureSelection, 70);
    }

    document.addEventListener("pointerup", scheduleCapture);
    document.addEventListener("touchend", scheduleCapture, { passive: true });
    document.addEventListener("keyup", scheduleCapture);
    document.addEventListener("selectionchange", scheduleCapture);
    return () => {
      document.removeEventListener("pointerup", scheduleCapture);
      document.removeEventListener("touchend", scheduleCapture);
      document.removeEventListener("keyup", scheduleCapture);
      document.removeEventListener("selectionchange", scheduleCapture);
      if (selectionTimer.current != null) window.clearTimeout(selectionTimer.current);
    };
  }, []);

  const selectedAnnotation = useMemo(() => {
    if (!selection) return null;
    return annotations.find((item) => item.partNumber === selection.partNumber
      && item.paragraphIndex === selection.paragraphIndex
      && item.startOffset === selection.startOffset
      && item.endOffset === selection.endOffset) || null;
  }, [annotations, selection]);

  function persist(next: ReadingAnnotation[]) {
    if (!context) return;
    setAnnotations(writeReadingAnnotationDraft(context.testId, context.testTitle, next));
  }

  function makeAnnotation(kind: AnnotationKind, note = ""): ReadingAnnotation | null {
    if (!selection) return null;
    const now = new Date().toISOString();
    return {
      id: selectedAnnotation?.id || annotationId(),
      kind,
      testId: selection.testId,
      testTitle: selection.testTitle,
      partNumber: selection.partNumber,
      paragraphIndex: selection.paragraphIndex,
      startOffset: selection.startOffset,
      endOffset: selection.endOffset,
      selectedText: selection.selectedText,
      prefix: normalizeReadingText(selection.paragraphText.slice(Math.max(0, selection.startOffset - 40), selection.startOffset)),
      suffix: normalizeReadingText(selection.paragraphText.slice(selection.endOffset, selection.endOffset + 40)),
      sentence: selection.sentence,
      note,
      createdAt: selectedAnnotation?.createdAt || now,
      updatedAt: now
    };
  }

  function closeSelection() {
    window.getSelection()?.removeAllRanges();
    setSelection(null);
    setNoteOpen(false);
  }

  function saveHighlight() {
    const annotation = makeAnnotation("highlight");
    if (!annotation) return;
    persist([annotation, ...annotations.filter((item) => item.id !== annotation.id)]);
    setStatus("已高亮，并同步到本机考试草稿");
    closeSelection();
  }

  function saveNote() {
    const annotation = makeAnnotation("note", noteDraft.trim());
    if (!annotation || !annotation.note) return;
    persist([annotation, ...annotations.filter((item) => item.id !== annotation.id)]);
    setStatus("笔记已保存，并同步到本机考试草稿");
    closeSelection();
  }

  async function addVocabulary() {
    if (!selection || savingVocabulary) return;
    setSavingVocabulary(true);
    setStatus("");
    try {
      await captureVocabulary({
        term: selection.selectedText,
        source_type: "reading_text",
        source_sentence: selection.sentence,
        source_context: `Part ${selection.partNumber} · 段落 ${selection.paragraphIndex + 1}`,
        test_id: selection.testId,
        test_title: selection.testTitle,
        part_number: selection.partNumber
      });
      setStatus("已加入词汇本，并自动保存原句与来源");
      closeSelection();
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "加入词汇本失败");
    } finally {
      setSavingVocabulary(false);
    }
  }

  function removeAnnotation(id: string) {
    persist(annotations.filter((item) => item.id !== id));
  }

  function editAnnotation(item: ReadingAnnotation) {
    const next = window.prompt("修改笔记", item.note);
    if (next === null) return;
    if (!next.trim()) {
      removeAnnotation(item.id);
      return;
    }
    persist(annotations.map((annotation) => annotation.id === item.id
      ? { ...annotation, kind: "note", note: next.trim(), updatedAt: new Date().toISOString() }
      : annotation));
  }

  const historyMode = !context && Boolean(history?.annotations.length) && Boolean(document.querySelector(".result-page"));
  if (!mounted || (!context && !historyMode)) return null;

  return createPortal(
    <>
      {context && selection ? (
        <div
          className="reading-selection-toolbar"
          style={{ left: Math.max(12, Math.min(selection.rect.left, window.innerWidth - 340)), top: Math.max(12, selection.rect.top - 52) }}
          role="toolbar"
          aria-label="阅读划词工具栏"
          onPointerDown={(event) => event.preventDefault()}
        >
          <button type="button" onClick={saveHighlight}>高亮</button>
          <button type="button" onClick={() => { setNoteOpen(true); setNoteDraft(selectedAnnotation?.note || ""); }}>笔记</button>
          <button type="button" disabled={savingVocabulary} onClick={() => void addVocabulary()}>{savingVocabulary ? "保存中…" : "加入词汇本"}</button>
          <button type="button" className="quiet" onClick={closeSelection}>取消</button>
        </div>
      ) : null}

      {context && selection && noteOpen ? (
        <div className="reading-note-editor" style={{ left: Math.max(12, Math.min(selection.rect.left, window.innerWidth - 360)), top: Math.min(window.innerHeight - 220, selection.rect.bottom + 12) }}>
          <strong>给“{selection.selectedText}”添加笔记</strong>
          <textarea autoFocus rows={4} value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="写下释义、同义替换或句子理解…" />
          <div><button type="button" className="secondary-button" onClick={() => setNoteOpen(false)}>取消</button><button type="button" className="primary-button" disabled={!noteDraft.trim()} onClick={saveNote}>保存笔记</button></div>
        </div>
      ) : null}

      {visibleAnnotations.length ? (
        <button type="button" className="reading-annotation-toggle" onClick={() => setPanelOpen((value) => !value)}>
          {historyMode ? "历史标注" : "标注"} {visibleAnnotations.length}
        </button>
      ) : null}

      {panelOpen && visibleAnnotations.length ? (
        <aside className="reading-annotation-panel" aria-label={historyMode ? "历史阅读标注" : "本页阅读标注"}>
          <div className="reading-annotation-panel-heading">
            <div><span>{historyMode ? "SESSION ANNOTATIONS" : "READING NOTES"}</span><strong>{historyMode ? history?.testTitle : "本页标注"}</strong></div>
            <button type="button" onClick={() => setPanelOpen(false)}>关闭</button>
          </div>
          <div className="reading-annotation-list">
            {visibleAnnotations.map((item) => (
              <article key={item.id}>
                <span>{item.kind === "note" ? "笔记" : "高亮"} · Part {item.partNumber} · 段落 {item.paragraphIndex + 1}</span>
                <strong>{item.selectedText}</strong>
                {item.note ? <p>{item.note}</p> : null}
                <HighlightedSentence annotation={item} />
                {!historyMode ? <div>{item.kind === "note" ? <button type="button" onClick={() => editAnnotation(item)}>编辑</button> : null}<button type="button" onClick={() => removeAnnotation(item.id)}>删除</button></div> : null}
              </article>
            ))}
          </div>
        </aside>
      ) : null}

      {status ? <div className="reading-annotation-status" role="status">{status}<button type="button" onClick={() => setStatus("")}>×</button></div> : null}
    </>,
    document.body
  );
}
