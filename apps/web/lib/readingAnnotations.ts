export type AnnotationKind = "highlight" | "note";

export type ReadingAnnotation = {
  id: string;
  kind: AnnotationKind;
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
type AnnotationDraft = {
  version: 1;
  testId: string;
  testTitle: string;
  updatedAt: string;
  annotations: ReadingAnnotation[];
};

const CURRENT_TEST_KEY = "ielts-platform-current-reading-test";
const ANNOTATION_DRAFT_PREFIX = "ielts-platform-reading-draft:";
const LEGACY_PREFIX = "ielts-platform-reading-annotations:";
export const READING_HISTORY_EVENT = "ielts-reading-history-loaded";

export function normalizeReadingText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

export function rememberCurrentReadingTest(test: CurrentTest): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(CURRENT_TEST_KEY, JSON.stringify(test));
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

function annotationDraftKey(testId: string): string {
  return `${ANNOTATION_DRAFT_PREFIX}${encodeURIComponent(testId)}`;
}

function isAnnotation(value: unknown): value is ReadingAnnotation {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ReadingAnnotation>;
  return typeof item.id === "string"
    && (item.kind === "highlight" || item.kind === "note")
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

function legacyAnnotation(
  value: unknown,
  options: { testId: string; testTitle: string; fallbackPartNumber: number }
): ReadingAnnotation | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const upgraded = {
    ...item,
    testId: options.testId,
    testTitle: options.testTitle,
    partNumber: Number(item.partNumber ?? options.fallbackPartNumber),
    paragraphIndex: Number(item.paragraphIndex),
    startOffset: Number(item.startOffset),
    endOffset: Number(item.endOffset),
    prefix: String(item.prefix ?? ""),
    suffix: String(item.suffix ?? ""),
    sentence: String(item.sentence ?? ""),
    note: String(item.note ?? "")
  };
  return isAnnotation(upgraded) ? upgraded : null;
}

function migrateLegacyAnnotations(testId: string, testTitle: string): ReadingAnnotation[] {
  if (typeof window === "undefined") return [];
  const prefix = `${LEGACY_PREFIX}${encodeURIComponent(testTitle)}:`;
  const migrated: ReadingAnnotation[] = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key?.startsWith(prefix)) continue;
    const fallbackPartNumber = Number(key.slice(prefix.length)) || 1;
    try {
      const parsed = JSON.parse(window.localStorage.getItem(key) || "[]") as unknown;
      if (!Array.isArray(parsed)) continue;
      for (const value of parsed) {
        const row = legacyAnnotation(value, { testId, testTitle, fallbackPartNumber });
        if (row) migrated.push(row);
      }
    } catch {
      // Invalid legacy drafts are ignored rather than overwriting valid learning data.
    }
  }
  return sanitizeReadingAnnotations(migrated);
}

export function readReadingAnnotationDraft(testId: string, testTitle = ""): ReadingAnnotation[] {
  if (typeof window === "undefined" || !testId) return [];
  try {
    const raw = window.localStorage.getItem(annotationDraftKey(testId));
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<AnnotationDraft>;
      return sanitizeReadingAnnotations(parsed.annotations);
    }
  } catch {
    // Fall through to safe migration.
  }
  const migrated = testTitle ? migrateLegacyAnnotations(testId, testTitle) : [];
  if (migrated.length) writeReadingAnnotationDraft(testId, testTitle, migrated);
  return migrated;
}

export function syncAnnotationsIntoExamDrafts(testId: string, annotations: ReadingAnnotation[]): void {
  if (typeof window === "undefined" || !testId) return;
  const prefix = `ielts-platform-draft:${testId}:`;
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key?.startsWith(prefix)) continue;
    try {
      const raw = window.localStorage.getItem(key);
      const draft = raw ? JSON.parse(raw) as Record<string, unknown> : {};
      const current = sanitizeReadingAnnotations(draft.annotations);
      if (JSON.stringify(current) === JSON.stringify(annotations)) continue;
      window.localStorage.setItem(key, JSON.stringify({ ...draft, annotations }));
    } catch {
      // A broken answer draft must not block annotation persistence.
    }
  }
}

export function writeReadingAnnotationDraft(
  testId: string,
  testTitle: string,
  annotations: ReadingAnnotation[]
): ReadingAnnotation[] {
  if (typeof window === "undefined" || !testId) return annotations;
  const clean = sanitizeReadingAnnotations(annotations);
  const draft: AnnotationDraft = {
    version: 1,
    testId,
    testTitle,
    updatedAt: new Date().toISOString(),
    annotations: clean
  };
  window.localStorage.setItem(annotationDraftKey(testId), JSON.stringify(draft));
  syncAnnotationsIntoExamDrafts(testId, clean);
  return clean;
}

export function readAnnotationsForSubmission(testId: string, partNumbers: number[]): ReadingAnnotation[] {
  const selected = new Set(partNumbers.map(Number));
  const rows = readReadingAnnotationDraft(testId);
  return selected.size ? rows.filter((item) => selected.has(item.partNumber)) : rows;
}

export function cacheSessionAnnotations(detail: ReadingHistoryDetail): void {
  if (typeof window === "undefined") return;
  const rows = sanitizeReadingAnnotations(detail.annotations).map((item) => ({
    ...item,
    testId: detail.testId,
    testTitle: detail.testTitle
  }));
  if (rows.length) {
    const existing = readReadingAnnotationDraft(detail.testId, detail.testTitle);
    const merged = sanitizeReadingAnnotations([...existing, ...rows]);
    writeReadingAnnotationDraft(detail.testId, detail.testTitle, merged);
  }
  window.setTimeout(() => {
    window.dispatchEvent(new CustomEvent<ReadingHistoryDetail>(READING_HISTORY_EVENT, {
      detail: { ...detail, annotations: rows }
    }));
  }, 0);
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
