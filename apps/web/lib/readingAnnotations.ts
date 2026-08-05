export type AnnotationKind = "highlight" | "note";

export type ReadingAnnotation = {
  id: string;
  kind: AnnotationKind;
  highlightLevel?: "primary" | "secondary";
  testId: string;
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

export type ReadingHistoryDetail = {
  sessionId: string;
  testId: string;
  testTitle: string;
  annotations: ReadingAnnotation[];
};

type CurrentTest = { id: string; title: string };
export type ReadingAttemptDetail = {
  attemptId: string;
  testId: string;
  testTitle: string;
  annotations: ReadingAnnotation[];
};

const CURRENT_TEST_KEY = "ielts-platform-current-reading-test";
export const READING_HISTORY_EVENT = "ielts-reading-history-loaded";
export const READING_ATTEMPT_EVENT = "ielts-reading-attempt-changed";
export const READING_ANNOTATIONS_EVENT = "ielts-reading-annotations-changed";

let activeReadingAttempt: ReadingAttemptDetail | null = null;

export function normalizeReadingText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function rememberCurrentReadingTest(test: CurrentTest): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(CURRENT_TEST_KEY, JSON.stringify(test));
  } catch {
    // Session storage is a convenience for annotation context. A browser that
    // blocks or exhausts storage must not make the verified question-bank
    // request appear to have failed.
  }
}

export function currentReadingTest(expectedTitle = ""): CurrentTest | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(CURRENT_TEST_KEY);
    const parsed = raw ? JSON.parse(raw) as Partial<CurrentTest> : null;
    if (!parsed || typeof parsed.id !== "string" || typeof parsed.title !== "string") return null;
    if (expectedTitle && normalizeReadingText(parsed.title) !== normalizeReadingText(expectedTitle)) return null;
    return { id: parsed.id, title: parsed.title };
  } catch {
    return null;
  }
}

function isAnnotation(value: unknown): value is ReadingAnnotation {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ReadingAnnotation>;
  return typeof item.id === "string"
    && (item.kind === "highlight" || item.kind === "note")
    && (
      item.highlightLevel == null
      || item.highlightLevel === "primary"
      || item.highlightLevel === "secondary"
    )
    && typeof item.testId === "string"
    && typeof item.testTitle === "string"
    && Number.isInteger(item.partNumber)
    && Number.isInteger(item.paragraphIndex)
    && typeof item.startOffset === "number"
    && typeof item.endOffset === "number"
    && typeof item.selectedText === "string"
    && typeof item.prefix === "string"
    && typeof item.suffix === "string"
    && typeof item.sentence === "string"
    && typeof item.note === "string"
    && typeof item.createdAt === "string"
    && typeof item.updatedAt === "string";
}

export function sanitizeReadingAnnotations(value: unknown): ReadingAnnotation[] {
  if (!Array.isArray(value)) return [];
  const byId = new Map<string, ReadingAnnotation>();
  for (const item of value) {
    if (!isAnnotation(item)) continue;
    if (item.startOffset < 0 || item.endOffset <= item.startOffset || item.selectedText.length > 300) continue;
    const existing = byId.get(item.id);
    if (!existing || item.updatedAt >= existing.updatedAt) byId.set(item.id, item);
  }
  return [...byId.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

function emitReadingEvent<T>(name: string, detail: T): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<T>(name, { detail }));
}

export function beginReadingAttempt(detail: ReadingAttemptDetail): ReadingAnnotation[] {
  const clean = sanitizeReadingAnnotations(detail.annotations).map((annotation) => ({
    ...annotation,
    testId: detail.testId,
    testTitle: detail.testTitle
  }));
  activeReadingAttempt = { ...detail, annotations: clean };
  emitReadingEvent(READING_ATTEMPT_EVENT, activeReadingAttempt);
  emitReadingEvent(READING_ANNOTATIONS_EVENT, activeReadingAttempt);
  return clean;
}

export function updateReadingAttemptAnnotations(
  testId: string,
  annotations: ReadingAnnotation[]
): ReadingAnnotation[] {
  if (!activeReadingAttempt || activeReadingAttempt.testId !== testId) return [];
  const clean = sanitizeReadingAnnotations(annotations);
  activeReadingAttempt = { ...activeReadingAttempt, annotations: clean };
  emitReadingEvent(READING_ANNOTATIONS_EVENT, activeReadingAttempt);
  return clean;
}

export function readAnnotationsForSubmission(testId: string, partNumbers: number[]): ReadingAnnotation[] {
  if (!activeReadingAttempt || activeReadingAttempt.testId !== testId) return [];
  const selected = new Set(partNumbers.map(Number));
  const rows = activeReadingAttempt.annotations;
  return selected.size ? rows.filter((item) => selected.has(item.partNumber)) : rows;
}

export function cacheSessionAnnotations(detail: ReadingHistoryDetail): void {
  const rows = sanitizeReadingAnnotations(detail.annotations).map((item) => ({
    ...item,
    testId: detail.testId,
    testTitle: detail.testTitle
  }));
  if (typeof window === "undefined") return;
  window.setTimeout(() => emitReadingEvent<ReadingHistoryDetail>(
    READING_HISTORY_EVENT,
    { ...detail, annotations: rows }
  ), 0);
}

type NormalizedMap = { text: string; rawIndexes: number[] };

function normalizeWithRawIndexes(value: string): NormalizedMap {
  let text = "";
  const rawIndexes: number[] = [];
  let pendingSpace = false;
  let pendingSpaceIndex = 0;
  for (let index = 0; index < value.length; index += 1) {
    const character = value[index];
    if (/\s/.test(character)) {
      if (text) {
        pendingSpace = true;
        pendingSpaceIndex = index;
      }
      continue;
    }
    if (pendingSpace) {
      text += " ";
      rawIndexes.push(pendingSpaceIndex);
      pendingSpace = false;
    }
    text += character;
    rawIndexes.push(index);
  }
  return { text, rawIndexes };
}

export function locateReadingAnnotation(
  paragraphText: string,
  annotation: Pick<ReadingAnnotation, "startOffset" | "endOffset" | "selectedText" | "prefix" | "suffix">
): { startOffset: number; endOffset: number } | null {
  const expected = normalizeReadingText(annotation.selectedText);
  if (!expected) return null;

  const direct = paragraphText.slice(annotation.startOffset, annotation.endOffset);
  if (normalizeReadingText(direct) === expected) {
    return { startOffset: annotation.startOffset, endOffset: annotation.endOffset };
  }

  const paragraph = normalizeWithRawIndexes(paragraphText);
  const selected = normalizeReadingText(annotation.selectedText);
  const prefix = normalizeReadingText(annotation.prefix);
  const suffix = normalizeReadingText(annotation.suffix);
  const anchor = normalizeReadingText(paragraphText.slice(0, Math.max(0, annotation.startOffset))).length;
  const candidates: Array<{ index: number; score: number }> = [];
  let cursor = paragraph.text.indexOf(selected);
  while (cursor >= 0) {
    const before = paragraph.text.slice(Math.max(0, cursor - prefix.length), cursor);
    const after = paragraph.text.slice(cursor + selected.length, cursor + selected.length + suffix.length);
    let score = -Math.abs(cursor - anchor);
    if (prefix && before.endsWith(prefix)) score += 1000;
    if (suffix && after.startsWith(suffix)) score += 1000;
    candidates.push({ index: cursor, score });
    cursor = paragraph.text.indexOf(selected, cursor + 1);
  }
  if (!candidates.length) return null;
  candidates.sort((a, b) => b.score - a.score);
  const startIndex = candidates[0].index;
  const endIndex = startIndex + selected.length - 1;
  const rawStart = paragraph.rawIndexes[startIndex];
  const rawEndCharacter = paragraph.rawIndexes[endIndex];
  if (rawStart == null || rawEndCharacter == null) return null;
  return { startOffset: rawStart, endOffset: rawEndCharacter + 1 };
}
