"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { captureVocabulary } from "@/lib/learningApi";

type AnnotationKind = "highlight" | "note";

type ReadingAnnotation = {
  id: string;
  kind: AnnotationKind;
  testTitle: string;
  partNumber: number;
  paragraphIndex: number;
  startOffset: number;
  endOffset: number;
  selectedText: string;
  prefix: string;
  suffix: string;
  sentence: string;
  note: string;
  createdAt: string;
  updatedAt: string;
};

type PendingSelection = {
  range: Range;
  rect: DOMRect;
  testTitle: string;
  partNumber: number;
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

const STORAGE_PREFIX = "ielts-platform-reading-annotations:";
const HIGHLIGHT_NAME = "reading-highlight";
const NOTE_NAME = "reading-note";

function annotationId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function currentContext(): { testTitle: string; partNumber: number } | null {
  const workbench = document.querySelector<HTMLElement>(".exam-workbench");
  if (!workbench) return null;
  const testTitle = normalizeText(workbench.querySelector<HTMLElement>(".exam-topbar > div:first-child strong")?.textContent || "");
  const activePartText = workbench.querySelector<HTMLElement>(".exam-part-tabs button.active")?.textContent || "";
  const match = activePartText.match(/(\d+)/);
  if (!testTitle || !match) return null;
  return { testTitle, partNumber: Number(match[1]) };
}

function storageKey(testTitle: string, partNumber: number): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(testTitle)}:${partNumber}`;
}

function loadAnnotations(testTitle: string, partNumber: number): ReadingAnnotation[] {
  try {
    const raw = window.localStorage.getItem(storageKey(testTitle, partNumber));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter(isAnnotation) : [];
  } catch {
    return [];
  }
}

function isAnnotation(value: unknown): value is ReadingAnnotation {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ReadingAnnotation>;
  return typeof item.id === "string"
    && (item.kind === "highlight" || item.kind === "note")
    && typeof item.testTitle === "string"
    && typeof item.partNumber === "number"
    && typeof item.paragraphIndex === "number"
    && typeof item.startOffset === "number"
    && typeof item.endOffset === "number"
    && typeof item.selectedText === "string";
}

function saveAnnotations(testTitle: string, partNumber: number, annotations: ReadingAnnotation[]): void {
  window.localStorage.setItem(storageKey(testTitle, partNumber), JSON.stringify(annotations));
}

function sentenceAround(text: string, start: number, end: number): string {
  const left = text.slice(0, start);
  const right = text.slice(end);
  const leftBoundary = Math.max(left.lastIndexOf("."), left.lastIndexOf("!"), left.lastIndexOf("?"), left.lastIndexOf("。"), left.lastIndexOf("！"), left.lastIndexOf("？"));
  const candidates = [right.indexOf("."), right.indexOf("!"), right.indexOf("?"), right.indexOf("。"), right.indexOf("！"), right.indexOf("？")].filter((value) => value >= 0);
  const rightBoundary = candidates.length ? Math.min(...candidates) + end + 1 : text.length;
  return normalizeText(text.slice(leftBoundary + 1, rightBoundary)) || normalizeText(text);
}

function textOffset(paragraph: HTMLElement, node: Node, offset: number): number {
  const range = document.createRange();
  range.selectNodeContents(paragraph);
  range.setEnd(node, offset);
  return range.toString().length;
}

function rangeForAnnotation(paragraph: HTMLElement, annotation: ReadingAnnotation): Range | null {
  const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
  let position = 0;
  let startNode: Text | null = null;
  let endNode: Text | null = null;
  let startOffset = 0;
  let endOffset = 0;
  while (walker.nextNode()) {
    const node = walker.currentNode as Text;
    const next = position + node.data.length;
    if (!startNode && annotation.startOffset >= position && annotation.startOffset <= next) {
      startNode = node;
      startOffset = annotation.startOffset - position;
    }
    if (annotation.endOffset >= position && annotation.endOffset <= next) {
      endNode = node;
      endOffset = annotation.endOffset - position;
      break;
    }
    position = next;
  }
  if (!startNode || !endNode) return null;
  const range = document.createRange();
  range.setStart(startNode, startOffset);
  range.setEnd(endNode, endOffset);
  if (normalizeText(range.toString()) !== normalizeText(annotation.selectedText)) return null;
  return range;
}

function highlightApi(): { registry: HighlightRegistry; Highlight: HighlightConstructor } | null {
  const css = globalThis.CSS as unknown as { highlights?: HighlightRegistry };
  const Highlight = (globalThis as unknown as { Highlight?: HighlightConstructor }).Highlight;
  return css?.highlights && Highlight ? { registry: css.highlights, Highlight } : null;
}

export default function ReadingAnnotationLayer() {
  const [mounted, setMounted] = useState(false);
  const [context, setContext] = useState<{ testTitle: string; partNumber: number } | null>(null);
  const [annotations, setAnnotations] = useState<ReadingAnnotation[]>([]);
  const [selection, setSelection] = useState<PendingSelection | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [savingVocabulary, setSavingVocabulary] = useState(false);

  useEffect(() => setMounted(true), []);

  const refreshContext = useCallback(() => {
    const next = currentContext();
    setContext((current) => {
      if (current?.testTitle === next?.testTitle && current?.partNumber === next?.partNumber) return current;
      return next;
    });
  }, []);

  useEffect(() => {
    refreshContext();
    const onClick = () => window.setTimeout(refreshContext, 40);
    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, [refreshContext]);

  useEffect(() => {
    if (!context) {
      setAnnotations([]);
      return;
    }
    setAnnotations(loadAnnotations(context.testTitle, context.partNumber));
    setSelection(null);
    setNoteOpen(false);
    setPanelOpen(false);
  }, [context]);

  const applyHighlights = useCallback(() => {
    const api = highlightApi();
    if (!api || !context) return;
    const paragraphs = [...document.querySelectorAll<HTMLElement>(".passage-copy .passage-paragraph p")];
    const highlightRanges: Range[] = [];
    const noteRanges: Range[] = [];
    for (const annotation of annotations) {
      const paragraph = paragraphs[annotation.paragraphIndex];
      if (!paragraph) continue;
      const range = rangeForAnnotation(paragraph, annotation);
      if (!range) continue;
      if (annotation.kind === "note") noteRanges.push(range);
      else highlightRanges.push(range);
    }
    api.registry.delete(HIGHLIGHT_NAME);
    api.registry.delete(NOTE_NAME);
    if (highlightRanges.length) api.registry.set(HIGHLIGHT_NAME, new api.Highlight(...highlightRanges));
    if (noteRanges.length) api.registry.set(NOTE_NAME, new api.Highlight(...noteRanges));
  }, [annotations, context]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(applyHighlights);
    const delayed = window.setTimeout(applyHighlights, 80);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(delayed);
    };
  }, [applyHighlights]);

  useEffect(() => {
    function captureSelection() {
      const browserSelection = window.getSelection();
      if (!browserSelection || browserSelection.isCollapsed || browserSelection.rangeCount !== 1) {
        setSelection(null);
        return;
      }
      const range = browserSelection.getRangeAt(0);
      const startElement = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer as HTMLElement;
      const endElement = range.endContainer.nodeType === Node.TEXT_NODE ? range.endContainer.parentElement : range.endContainer as HTMLElement;
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
      const selectedText = normalizeText(range.toString());
      if (!selectedText || selectedText.length > 300) {
        setSelection(null);
        return;
      }
      const startOffset = textOffset(paragraph, range.startContainer, range.startOffset);
      const endOffset = textOffset(paragraph, range.endContainer, range.endOffset);
      const paragraphText = paragraph.textContent || "";
      setSelection({
        range: range.cloneRange(),
        rect: range.getBoundingClientRect(),
        ...nextContext,
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

    document.addEventListener("pointerup", captureSelection);
    document.addEventListener("keyup", captureSelection);
    return () => {
      document.removeEventListener("pointerup", captureSelection);
      document.removeEventListener("keyup", captureSelection);
    };
  }, []);

  const selectedAnnotation = useMemo(() => {
    if (!selection) return null;
    return annotations.find((item) => item.paragraphIndex === selection.paragraphIndex
      && item.startOffset === selection.startOffset
      && item.endOffset === selection.endOffset) || null;
  }, [annotations, selection]);

  function persist(next: ReadingAnnotation[]) {
    if (!context) return;
    setAnnotations(next);
    saveAnnotations(context.testTitle, context.partNumber, next);
  }

  function makeAnnotation(kind: AnnotationKind, note = ""): ReadingAnnotation | null {
    if (!selection) return null;
    const now = new Date().toISOString();
    return {
      id: selectedAnnotation?.id || annotationId(),
      kind,
      testTitle: selection.testTitle,
      partNumber: selection.partNumber,
      paragraphIndex: selection.paragraphIndex,
      startOffset: selection.startOffset,
      endOffset: selection.endOffset,
      selectedText: selection.selectedText,
      prefix: normalizeText(selection.paragraphText.slice(Math.max(0, selection.startOffset - 32), selection.startOffset)),
      suffix: normalizeText(selection.paragraphText.slice(selection.endOffset, selection.endOffset + 32)),
      sentence: selection.sentence,
      note,
      createdAt: selectedAnnotation?.createdAt || now,
      updatedAt: now
    };
  }

  function saveHighlight() {
    const annotation = makeAnnotation("highlight");
    if (!annotation) return;
    persist([annotation, ...annotations.filter((item) => item.id !== annotation.id)]);
    setStatus("已高亮并保存到本机草稿");
    window.getSelection()?.removeAllRanges();
    setSelection(null);
  }

  function saveNote() {
    const annotation = makeAnnotation("note", noteDraft.trim());
    if (!annotation || !annotation.note) return;
    persist([annotation, ...annotations.filter((item) => item.id !== annotation.id)]);
    setStatus("笔记已保存到本机草稿");
    setNoteOpen(false);
    window.getSelection()?.removeAllRanges();
    setSelection(null);
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
        test_title: selection.testTitle,
        part_number: selection.partNumber
      });
      setStatus("已加入词汇本，并自动保存原句与来源");
      window.getSelection()?.removeAllRanges();
      setSelection(null);
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

  if (!mounted || !context) return null;

  return createPortal(
    <>
      {selection ? (
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
          <button type="button" className="quiet" onClick={() => { window.getSelection()?.removeAllRanges(); setSelection(null); }}>取消</button>
        </div>
      ) : null}

      {selection && noteOpen ? (
        <div className="reading-note-editor" style={{ left: Math.max(12, Math.min(selection.rect.left, window.innerWidth - 360)), top: Math.min(window.innerHeight - 220, selection.rect.bottom + 12) }}>
          <strong>给“{selection.selectedText}”添加笔记</strong>
          <textarea autoFocus rows={4} value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="写下释义、同义替换或句子理解…" />
          <div><button type="button" className="secondary-button" onClick={() => setNoteOpen(false)}>取消</button><button type="button" className="primary-button" disabled={!noteDraft.trim()} onClick={saveNote}>保存笔记</button></div>
        </div>
      ) : null}

      {annotations.length ? <button type="button" className="reading-annotation-toggle" onClick={() => setPanelOpen((value) => !value)}>标注 {annotations.length}</button> : null}
      {panelOpen ? (
        <aside className="reading-annotation-panel" aria-label="本页阅读标注">
          <div className="reading-annotation-panel-heading"><div><span>READING NOTES</span><strong>本页标注</strong></div><button type="button" onClick={() => setPanelOpen(false)}>关闭</button></div>
          <div className="reading-annotation-list">
            {annotations.map((item) => (
              <article key={item.id}>
                <span>{item.kind === "note" ? "笔记" : "高亮"} · 段落 {item.paragraphIndex + 1}</span>
                <strong>{item.selectedText}</strong>
                {item.note ? <p>{item.note}</p> : null}
                <small>{item.sentence}</small>
                <div>{item.kind === "note" ? <button type="button" onClick={() => editAnnotation(item)}>编辑</button> : null}<button type="button" onClick={() => removeAnnotation(item.id)}>删除</button></div>
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
