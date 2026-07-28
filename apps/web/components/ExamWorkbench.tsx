"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  fetchPublicTest,
  fetchSession,
  fetchSessions,
  fetchTests,
  submitSession,
  type PublicPart,
  type PublicQuestion,
  type PublicQuestionGroup,
  type PublicTest,
  type QuestionOption,
  type ScoringResult,
  type SessionSummary,
  type TestIndexItem
} from "@/lib/api";

type ExamMode = "mock_exam" | "study" | "part_practice";
type Screen = "library" | "exam" | "result";
type AnswerValue = string | string[];

type DraftState = {
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  elapsedSeconds: number;
  remainingSeconds: number | null;
  partElapsedSeconds?: Record<string, number>;
  questionElapsedSeconds?: Record<string, number>;
  activeQuestionId?: string;
  clientSubmissionId: string;
  testTitle?: string;
  mode?: ExamMode;
  partNumbers?: number[];
  updatedAt?: string;
};
type DraftSummary = DraftState & { key: string; testId: string };

const USER_ID = "owner";
const READING_FONT_SIZES = [15, 17, 19, 21, 23] as const;
const PANE_RATIO_STORAGE_KEY = "ielts-exam-pane-ratio-v2";

function normalizeReadingFontSize(value: unknown): number {
  if (value === null || value === undefined || String(value).trim() === "") return 17;
  const size = Number(value);
  if (!Number.isFinite(size)) return 17;
  return READING_FONT_SIZES.reduce((closest, candidate) =>
    Math.abs(candidate - size) < Math.abs(closest - size) ? candidate : closest, 17);
}

function formatSeconds(value: number): string {
  const safe = Math.max(0, Math.floor(value));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function questionNumber(question: PublicQuestion): string {
  return String(question.display_number ?? question.number);
}

function partQuestionRange(part: PublicPart): string {
  const numbers = part.groups
    .flatMap((group) => group.questions)
    .map((question) => Number(question.display_number ?? question.number))
    .filter(Number.isFinite);
  if (!numbers.length) return "";
  const start = Math.min(...numbers);
  const end = Math.max(...numbers);
  return start === end ? String(start) : `${start}–${end}`;
}

const GENERIC_PASSAGE_TITLE = /^(?:part\s+\d+\s+reading texts|passage\s+\d+)$/i;

function normalizedPassageTitle(value: unknown): string {
  return repairDisplayText(String(value || ""))
    .replace(/\s+/g, " ")
    .trim()
    .toLocaleLowerCase();
}

function resolvedPassageTitle(part: PublicPart): string {
  const articleTitle = repairDisplayText(String(part.article_title || part.title || "")).trim();
  if (!GENERIC_PASSAGE_TITLE.test(articleTitle)) return articleTitle;

  const sourceTitle = repairDisplayText(String(part.source_article_title || "")).trim();
  if (!sourceTitle || GENERIC_PASSAGE_TITLE.test(sourceTitle)) return articleTitle;

  const normalizedSourceTitle = normalizedPassageTitle(sourceTitle);
  const sourceTitleAppearsInBody = (part.paragraphs || []).some(
    (paragraph) => normalizedPassageTitle(paragraph.text) === normalizedSourceTitle
  );
  return sourceTitleAppearsInBody ? "" : sourceTitle;
}

function looksLikePassageHeading(text: string, index: number, paragraphs: NonNullable<PublicPart["paragraphs"]>): boolean {
  const value = text.trim();
  if (!value || value.length > 90 || /[.!]$/.test(value) || /^[-•·▪●]/.test(value)) return false;
  if (/\s[-–—]\s/.test(value)) return false;
  if (/^[A-Z]$/.test(value) || /^[ivxlcdm]{1,5}$/i.test(value) || /^\([^)]*\)$/.test(value)) return false;
  const words = value.split(/\s+/);
  if (words.length > 12) return false;

  const nextText = String(paragraphs[index + 1]?.text || "").trim();
  if (nextText.length <= 45 && !/^[-•·▪●]/.test(nextText)) return false;

  const obviousProse = /^(?:for example|for every)\b/i.test(value)
    || (/^(?:this|these|those|it|they|he|she|we|i|however|although|because|since|while|meanwhile)\b/i.test(value)
      && words.length >= 6);
  const namedSubjectProse = /^[A-Za-z][\w&'.-]*(?:\s+[A-Za-z][\w&'.-]*){0,3}\s+(?:is|are|has|have|offers|provides|will|can)\b/i.test(value)
    && words.length >= 8;
  if (obviousProse || namedSubjectProse) return false;

  const previousText = String(paragraphs[index - 1]?.text || "").trim();
  const separatedFromBody = index === 0
    || previousText.length > 45
    || /[.!?]$/.test(previousText)
    || /^[-•·▪●]/.test(previousText);
  const titleLike = value === value.toUpperCase()
    || words.filter((word) => /^[A-Z][a-z]/.test(word)).length >= Math.ceil(words.length / 2);
  return titleLike || separatedFromBody;
}

function looksLikePassageCategory(text: string): boolean {
  const value = text.trim();
  return /^(?:for\s+(?:under|over)|under|over)\s+[$£€]\s*\d+/i.test(value)
    || /^(?:additional\s+(?:monthly\s+)?specials?|note\s*:|within\s+[^:]+:|overseas\s*:)/i.test(value);
}

function passageListingParts(text: string): { label: string; detail: string } | null {
  const match = text.trim().match(/^([^.!?,;:]{2,48})\s[-–—]\s(.+)$/);
  return match ? { label: match[1].trim(), detail: match[2].trim() } : null;
}

function PassageTable({ paragraph }: { paragraph: NonNullable<PublicPart["paragraphs"]>[number] }) {
  const table = paragraph.table;
  if (!table) return null;
  return (
    <div className="passage-source-table passage-unit">
      <table>
        {table.caption ? <caption>{table.caption}</caption> : null}
        {table.intro ? (
          <thead>
            <tr><td colSpan={Math.max(1, table.headers.length)}>{table.intro}</td></tr>
            <tr>{table.headers.map((header) => <th scope="col" key={header}>{header}</th>)}</tr>
          </thead>
        ) : (
          <thead><tr>{table.headers.map((header) => <th scope="col" key={header}>{header}</th>)}</tr></thead>
        )}
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={`passage-table-row-${rowIndex}`}>
              {row.map((cell, cellIndex) => {
                const Cell = cellIndex === 0 ? "th" : "td";
                return <Cell scope={cellIndex === 0 ? "row" : undefined} key={`passage-table-cell-${cellIndex}`}>{cell}</Cell>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {table.notes?.length ? (
        <div className="passage-source-table-notes">
          {table.notes.map((note) => <p key={note}>{note}</p>)}
        </div>
      ) : null}
    </div>
  );
}

const INSTRUCTION_EMPHASIS = /\b(NO MORE THAN(?:\s+[A-Z]+){0,5}|ONE WORD ONLY|TRUE|FALSE|NOT GIVEN|YES|NO|A NUMBER)\b/g;
const INSTRUCTION_EMPHASIS_EXACT = /^(?:NO MORE THAN(?:\s+[A-Z]+){0,5}|ONE WORD ONLY|TRUE|FALSE|NOT GIVEN|YES|NO|A NUMBER)$/;

function InstructionLine({ children }: { children: string }) {
  return (
    <>
      {children.split(INSTRUCTION_EMPHASIS).map((part, index) =>
        INSTRUCTION_EMPHASIS_EXACT.test(part)
          ? <strong key={`${part}-${index}`}>{part}</strong>
          : <Fragment key={`${part}-${index}`}>{part}</Fragment>
      )}
    </>
  );
}

function normalizeInstructionDetails(lines: string[]): string[] {
  return lines.flatMap((line) => {
    const classify = line.match(
      /^(Classify the following .+?)\s+as (?:being|referring to)\s+.+?\s+((?:Choose|Write)\s+.+)$/i
    );
    if (!classify) return [line];
    const prompt = `${classify[1].replace(/[.。]+$/, "")}.`;
    const action = classify[2].replace(/\bcorrect word\b/i, "correct option");
    return [prompt, action];
  });
}

function QuestionInstructions({ group }: { group: PublicQuestionGroup }) {
  const lines = String(group.instructions || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const range = lines[0] || group.question_label || group.question_subtype;
  const details = normalizeInstructionDetails(lines.slice(1));
  return (
    <div className="question-instructions question-annotation-unit">
      <div className="question-instructions-heading">
        <strong>{range}</strong>
        <span>{group.question_label || group.question_subtype}</span>
      </div>
      <div className="question-instructions-copy">
        {details.map((line, index) => <p key={`${line}-${index}`}><InstructionLine>{line}</InstructionLine></p>)}
      </div>
    </div>
  );
}

function normalizeOption(value: unknown, index: number): QuestionOption | null {
  if (typeof value === "string") {
    const match = value.trim().match(/^([A-Za-z]+|[ivxlcdm]+)[.):\s-]+(.*)$/i);
    return match
      ? { code: match[1], text: match[2] || match[1] }
      : { code: value.trim() || String(index + 1), text: value.trim() };
  }
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    const code = String(item.code ?? item.value ?? item.title ?? index + 1).trim();
    const text = String(item.text ?? item.label ?? item.content ?? code).trim();
    return code ? { code, text } : null;
  }
  return null;
}

function restoreInstructionOptionText(options: QuestionOption[], instructions = ""): QuestionOption[] {
  if (!options.length || options.some((option) => optionDisplayText(option))) return options;
  const copy = instructions.replace(/\s+/g, " ").trim();
  if (!/\bclassify\b/i.test(copy)) return options;
  return options.map((option, index) => {
    const nextCode = options[index + 1]?.code;
    const end = nextCode
      ? `(?=\\s+${nextCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s+)`
      : "(?=\\s+(?:Choose|Write)\\b|$)";
    const code = option.code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = copy.match(new RegExp(`(?:^|\\s)${code}\\s+(.+?)${end}`, "i"));
    return match ? { ...option, text: match[1].trim() } : option;
  });
}

function optionsFor(group: PublicQuestionGroup, question: PublicQuestion): QuestionOption[] {
  if (question.options?.length) {
    const questionOptions = restoreInstructionOptionText(
      question.options.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item)),
      group.instructions
    );
    if (group.normalized_options?.length) {
      const groupOptions = restoreInstructionOptionText(group.normalized_options, group.instructions);
      const groupOptionsByCode = new Map(groupOptions.map((option) => [option.code, option]));
      return questionOptions.map((option) =>
        optionDisplayText(option)
          ? option
          : groupOptionsByCode.get(option.code) || option
      );
    }
    return questionOptions;
  }
  if (group.normalized_options?.length) {
    return restoreInstructionOptionText(group.normalized_options, group.instructions);
  }
  const raw = Array.isArray(group.shared_options) && group.shared_options.length
    ? group.shared_options
    : group.options || [];
  return restoreInstructionOptionText(
    raw.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item)),
    group.instructions
  );
}

function selectedParts(test: PublicTest | null, partNumbers: number[]): PublicPart[] {
  if (!test) return [];
  if (!partNumbers.length) return test.parts;
  const selected = new Set(partNumbers);
  return test.parts.filter((part) => selected.has(Number(part.number)));
}

function allQuestionRows(test: PublicTest | null, partNumbers: number[]) {
  return selectedParts(test, partNumbers).flatMap((part) =>
    part.groups.flatMap((group) =>
      group.questions.map((question) => ({ part, group, question }))
    )
  );
}

function sharedQuestionIds(group: PublicQuestionGroup): string[] {
  if (!group.shared_response) return [];
  const declared = group.shared_response_question_ids || [];
  return declared.length
    ? declared.map(String)
    : group.questions.map((question) => String(question.id));
}

function controlQuestionId(group: PublicQuestionGroup, question: PublicQuestion): string {
  return sharedQuestionIds(group)[0] || String(question.id);
}

function firstQuestionId(part?: PublicPart): string {
  const group = part?.groups.find((item) => item.questions.length);
  const question = group?.questions[0];
  return group && question ? controlQuestionId(group, question) : "";
}

function submittedQuestionTimings(
  test: PublicTest,
  partNumbers: number[],
  timings: Record<string, number>
): Record<string, number> {
  const submitted: Record<string, number> = {};
  for (const part of selectedParts(test, partNumbers)) {
    for (const group of part.groups) {
      const ids = group.questions.map((question) => String(question.id));
      if (!ids.length) continue;
      if (!group.shared_response || ids.length === 1) {
        for (const id of ids) submitted[id] = Math.max(0, Math.floor(timings[id] || 0));
        continue;
      }
      const total = ids.reduce((sum, id) => sum + Math.max(0, Math.floor(timings[id] || 0)), 0);
      const base = Math.floor(total / ids.length);
      let remainder = total % ids.length;
      for (const id of ids) {
        submitted[id] = base + (remainder > 0 ? 1 : 0);
        remainder = Math.max(0, remainder - 1);
      }
    }
  }
  return submitted;
}

function controlQuestion(group: PublicQuestionGroup, question: PublicQuestion): PublicQuestion {
  if (!group.shared_response) return question;
  const numbers = group.shared_response_numbers?.length
    ? group.shared_response_numbers
    : group.questions.map((item) => Number(item.display_number ?? item.number));
  return {
    ...question,
    display_number: numbers.length > 1
      ? `${numbers[0]}–${numbers[numbers.length - 1]}`
      : String(numbers[0] ?? questionNumber(question))
  };
}

function newSubmissionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `web-${crypto.randomUUID()}`;
  }
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function modeLabel(mode: ExamMode): string {
  if (mode === "mock_exam") return "60分钟模拟考试";
  if (mode === "part_practice") return "单Part训练";
  return "整套学习";
}

export default function ExamWorkbench() {
  const [screen, setScreen] = useState<Screen>("library");
  const [tests, setTests] = useState<TestIndexItem[]>([]);
  const [history, setHistory] = useState<SessionSummary[]>([]);
  const [test, setTest] = useState<PublicTest | null>(null);
  const [mode, setMode] = useState<ExamMode>("mock_exam");
  const [partNumbers, setPartNumbers] = useState<number[]>([]);
  const [activePart, setActivePart] = useState(1);
  const [mobilePane, setMobilePane] = useState<"passage" | "questions">("passage");
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [flagged, setFlagged] = useState<Record<string, boolean>>({});
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const [partElapsedSeconds, setPartElapsedSeconds] = useState<Record<string, number>>({});
  const [questionElapsedSeconds, setQuestionElapsedSeconds] = useState<Record<string, number>>({});
  const [activeQuestionId, setActiveQuestionId] = useState("");
  const [clientSubmissionId, setClientSubmissionId] = useState("");
  const [draftKey, setDraftKey] = useState("");
  const [result, setResult] = useState<ScoringResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [readingFontSize, setReadingFontSize] = useState(17);
  const [difficulty, setDifficulty] = useState<"all" | "easy" | "medium" | "hard">("all");
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [showDrafts, setShowDrafts] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [paused, setPaused] = useState(false);
  const [paneRatio, setPaneRatio] = useState(40);
  const timedOutRef = useRef(false);
  const activePartRef = useRef(1);
  const activeQuestionIdRef = useRef("");
  const activeQuestionLockUntilRef = useRef(0);
  const draftSnapshotRef = useRef<DraftState | null>(null);

  useEffect(() => {
    activeQuestionIdRef.current = activeQuestionId;
  }, [activeQuestionId]);

  useEffect(() => {
    activePartRef.current = activePart;
  }, [activePart]);

  useEffect(() => {
    setReadingFontSize(normalizeReadingFontSize(window.localStorage.getItem("ielts-passage-font-size")));
    const storedRatioValue = window.localStorage.getItem(PANE_RATIO_STORAGE_KEY);
    if (storedRatioValue !== null && storedRatioValue.trim() !== "") {
      const storedRatio = Number(storedRatioValue);
      if (Number.isFinite(storedRatio)) setPaneRatio(Math.max(30, Math.min(70, storedRatio)));
    }
    refreshDrafts();
  }, []);

  function refreshDrafts() {
    const rows: DraftSummary[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith("ielts-platform-draft:")) continue;
      try {
        const value = JSON.parse(window.localStorage.getItem(key) || "") as DraftState;
        const hasAnswers = Object.values(value.answers || {}).some(answerIsPresent);
        const hasFlags = Object.values(value.flagged || {}).some(Boolean);
        if (!hasAnswers && !hasFlags) continue;
        rows.push({ ...value, key, testId: key.split(":")[1] || "" });
      } catch {
        // Ignore malformed browser storage; no server data is affected.
      }
    }
    rows.sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    setDrafts(rows);
  }

  const refreshHistory = useCallback(async () => {
    try {
      setHistory(await fetchSessions(USER_ID));
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchTests(controller.signal), fetchSessions(USER_ID, controller.signal)])
      .then(([testItems, sessionItems]) => {
        setTests(testItems);
        setHistory(sessionItems);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "题库加载失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const currentParts = useMemo(() => selectedParts(test, partNumbers), [test, partNumbers]);
  const questionRows = useMemo(() => allQuestionRows(test, partNumbers), [test, partNumbers]);
  const answeredCount = useMemo(
    () => questionRows.filter(({ group, question }) => {
      const value = answers[String(question.id)];
      return answerIsComplete(group, value);
    }).length,
    [questionRows, answers]
  );
  const hasDraftProgress = answeredCount > 0 || Object.values(flagged).some(Boolean);

  draftSnapshotRef.current = screen === "exam" && draftKey && clientSubmissionId ? {
    answers,
    flagged,
    elapsedSeconds,
    remainingSeconds,
    partElapsedSeconds,
    questionElapsedSeconds,
    activeQuestionId,
    clientSubmissionId,
    testTitle: test?.title,
    mode,
    partNumbers,
    updatedAt: new Date().toISOString()
  } : null;

  useEffect(() => {
    if (screen !== "exam" || paused) return;
    const timer = window.setInterval(() => {
      setElapsedSeconds((value) => value + 1);
      const currentPartNumber = String(activePartRef.current);
      setPartElapsedSeconds((current) => ({
        ...current,
        [currentPartNumber]: (current[currentPartNumber] || 0) + 1
      }));
      const currentQuestionId = activeQuestionIdRef.current;
      if (currentQuestionId) {
        setQuestionElapsedSeconds((current) => ({
          ...current,
          [currentQuestionId]: (current[currentQuestionId] || 0) + 1
        }));
      }
      setRemainingSeconds((value) => {
        if (value === null) return null;
        if (value <= 1) {
          timedOutRef.current = true;
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [paused, screen]);

  useEffect(() => {
    if (screen !== "exam") return;
    const root = document.querySelector<HTMLElement>(".questions-pane");
    if (!root) return;
    const elements = [...root.querySelectorAll<HTMLElement>('[id^="question-"]')];
    if (!elements.length) return;
    const visible = new Map<Element, IntersectionObserverEntry>();
    const observer = new IntersectionObserver((entries) => {
      if (Date.now() < activeQuestionLockUntilRef.current) return;
      for (const entry of entries) {
        if (entry.isIntersecting) visible.set(entry.target, entry);
        else visible.delete(entry.target);
      }
      const rootRect = root.getBoundingClientRect();
      const targetTop = rootRect.top + rootRect.height * 0.46;
      const score = (entry: IntersectionObserverEntry) =>
        Math.abs(
          (entry.boundingClientRect.top + entry.boundingClientRect.bottom) / 2 - targetTop
        );
      const closest = [...visible.values()].sort((left, right) => score(left) - score(right))[0];
      const id = (closest?.target as HTMLElement | undefined)?.id;
      if (id?.startsWith("question-")) setActiveQuestionId(id.slice("question-".length));
    }, { root, rootMargin: "0px 0px -30% 0px", threshold: [0.01, 0.25, 0.5] });
    for (const element of elements) observer.observe(element);
    return () => observer.disconnect();
  }, [activePart, screen, test]);

  const persistCurrentDraft = useCallback((): DraftState | null => {
    if (screen !== "exam" || !draftKey || !clientSubmissionId) return null;
    const draft = draftSnapshotRef.current;
    if (!draft) return null;
    const hasAnswers = Object.values(draft.answers).some(answerIsPresent);
    const hasFlags = Object.values(draft.flagged).some(Boolean);
    if (!hasAnswers && !hasFlags) return null;
    window.localStorage.setItem(draftKey, JSON.stringify(draft));
    return draft;
  }, [clientSubmissionId, draftKey, screen]);

  const submitCurrent = useCallback(async (timedOut = false) => {
    if (!test || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitSession({
        user_id: USER_ID,
        test_id: test.id,
        client_submission_id: clientSubmissionId,
        answers,
        elapsed_seconds: elapsedSeconds,
        part_elapsed_seconds: Object.fromEntries(
          selectedParts(test, partNumbers).map((part) => {
            const key = String(part.number);
            return [key, Math.max(0, Math.floor(partElapsedSeconds[key] || 0))];
          })
        ),
        question_elapsed_seconds: submittedQuestionTimings(test, partNumbers, questionElapsedSeconds),
        exam_mode: mode,
        part_numbers: partNumbers,
        timed_out: timedOut
      });
      setResult(response.result);
      setScreen("result");
      if (draftKey) window.localStorage.removeItem(draftKey);
      await refreshHistory();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "交卷失败，请重试");
      timedOutRef.current = false;
    } finally {
      setSubmitting(false);
    }
  }, [answers, clientSubmissionId, draftKey, elapsedSeconds, mode, partElapsedSeconds, partNumbers, questionElapsedSeconds, refreshHistory, submitting, test]);

  useEffect(() => {
    if (screen === "exam" && timedOutRef.current && remainingSeconds === 0 && !submitting) {
      void submitCurrent(true);
    }
  }, [remainingSeconds, screen, submitCurrent, submitting]);

  async function startExam(
    testId: string,
    nextMode: ExamMode,
    nextParts: number[],
    resumeDraft = false,
    selectedDraft: DraftState | null = null
  ) {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const loaded = await fetchPublicTest(testId);
      const resolvedParts = nextParts.length ? nextParts : loaded.parts.map((part) => Number(part.number));
      const key = `ielts-platform-draft:${testId}:${nextMode}:${resolvedParts.join("-")}`;
      let draft: DraftState | null = null;
      if (resumeDraft) {
        draft = selectedDraft;
        if (!draft) {
          try {
            const raw = window.localStorage.getItem(key);
            draft = raw ? JSON.parse(raw) as DraftState : null;
          } catch {
            draft = null;
          }
        }
      } else {
        window.localStorage.removeItem(key);
        setDrafts((current) => current.filter((item) => item.key !== key));
      }
      const limit = nextMode === "mock_exam" ? 3600 : nextMode === "part_practice" ? 1200 : null;
      setTest(loaded);
      setMode(nextMode);
      setPartNumbers(nextParts);
      setActivePart(resolvedParts[0] || 1);
      setMobilePane("passage");
      setAnswers(draft?.answers || {});
      setFlagged(draft?.flagged || {});
      setElapsedSeconds(draft?.elapsedSeconds || 0);
      setRemainingSeconds(draft?.remainingSeconds ?? limit);
      setPartElapsedSeconds(draft?.partElapsedSeconds || {});
      setQuestionElapsedSeconds(draft?.questionElapsedSeconds || {});
      const availableQuestionIds = new Set(
        allQuestionRows(loaded, nextParts).map(({ group, question }) => controlQuestionId(group, question))
      );
      const restoredQuestionId = draft?.activeQuestionId && availableQuestionIds.has(draft.activeQuestionId)
        ? draft.activeQuestionId
        : firstQuestionId(selectedParts(loaded, nextParts)[0]);
      setActiveQuestionId(restoredQuestionId);
      setClientSubmissionId(draft?.clientSubmissionId || newSubmissionId());
      setDraftKey(key);
      setResult(null);
      timedOutRef.current = false;
      setPaused(false);
      if (draft) setNotice("已从草稿管理器继续上次未完成的答案和计时。");
      setScreen("exam");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "试卷加载失败");
    } finally {
      setLoading(false);
    }
  }

  function updateAnswer(questionIds: string | string[], value: AnswerValue) {
    const ids = Array.isArray(questionIds) ? questionIds : [questionIds];
    if (ids[0]) setActiveQuestionId(ids[0]);
    setAnswers((current) => {
      const next = { ...current };
      for (const questionId of ids) next[questionId] = value;
      return next;
    });
  }

  function toggleFlag(questionIds: string | string[]) {
    const ids = Array.isArray(questionIds) ? questionIds : [questionIds];
    if (ids[0]) setActiveQuestionId(ids[0]);
    setFlagged((current) => {
      const next = { ...current };
      const flagged = ids.some((questionId) => current[questionId]);
      for (const questionId of ids) next[questionId] = !flagged;
      return next;
    });
  }

  function scrollToQuestion(questionId: string, partNumber: number) {
    activeQuestionLockUntilRef.current = Date.now() + 1200;
    setActivePart(partNumber);
    setActiveQuestionId(questionId);
    setMobilePane("questions");
    window.setTimeout(() => {
      document.getElementById(`question-${questionId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 20);
  }

  function changeReadingFontSize(direction: -1 | 1) {
    const currentIndex = READING_FONT_SIZES.indexOf(readingFontSize as (typeof READING_FONT_SIZES)[number]);
    const safeIndex = currentIndex < 0 ? 2 : currentIndex;
    const nextIndex = Math.max(0, Math.min(READING_FONT_SIZES.length - 1, safeIndex + direction));
    const nextSize = READING_FONT_SIZES[nextIndex];
    setReadingFontSize(nextSize);
    window.localStorage.setItem("ielts-passage-font-size", String(nextSize));
  }

  function saveDraftManually(): boolean {
    const savedDraft = persistCurrentDraft();
    if (!savedDraft || !draftKey) {
      setNotice("请先作答或标记题目，再保存草稿。");
      return false;
    }
    const summary: DraftSummary = {
      ...savedDraft,
      key: draftKey,
      testId: draftKey.split(":")[1] || ""
    };
    setDrafts((current) => [summary, ...current.filter((item) => item.key !== draftKey)]);
    setNotice("草稿已手动保存。以后可从“管理草稿”继续。");
    return true;
  }

  function saveDraftAndLeave() {
    if (!saveDraftManually()) return;
    setPaused(false);
    setScreen("library");
    setNotice("");
  }

  function leaveExam() {
    if (hasDraftProgress && !window.confirm("当前答案不会自动保存。若需要保留，请先点击“保存草稿”。确定不保存并返回题库吗？")) return;
    setPaused(false);
    setScreen("library");
    setNotice("");
  }

  function beginDividerDrag(event: ReactPointerEvent<HTMLDivElement>) {
    const grid = event.currentTarget.parentElement;
    if (!grid) return;
    const move = (pointerEvent: PointerEvent) => {
      const rect = grid.getBoundingClientRect();
      setPaneRatio(Math.max(30, Math.min(70, ((pointerEvent.clientX - rect.left) / rect.width) * 100)));
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
      setPaneRatio((value) => {
        const rounded = Math.round(value);
        window.localStorage.setItem(PANE_RATIO_STORAGE_KEY, String(rounded));
        return rounded;
      });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
  }

  function adjustDividerFromKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    const direction = event.key === "ArrowLeft" ? -2 : event.key === "ArrowRight" ? 2 : 0;
    const fixedValue = event.key === "Home" ? 30 : event.key === "End" ? 70 : null;
    if (!direction && fixedValue === null) return;
    event.preventDefault();
    setPaneRatio((value) => {
      const next = fixedValue ?? Math.max(30, Math.min(70, value + direction));
      window.localStorage.setItem(PANE_RATIO_STORAGE_KEY, String(next));
      return next;
    });
  }

  async function openHistory(sessionId: string) {
    setLoading(true);
    setError("");
    try {
      const session = await fetchSession(sessionId, USER_ID);
      setResult(session.result);
      setTest(null);
      setScreen("result");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "记录读取失败");
    } finally {
      setLoading(false);
    }
  }

  const groupedTests = useMemo(() => {
    const groups = new Map<number, TestIndexItem[]>();
    for (const item of tests.filter((row) => difficulty === "all" || row.difficulty?.level === difficulty)) {
      const rows = groups.get(item.book_number) || [];
      rows.push(item);
      groups.set(item.book_number, rows);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [difficulty, tests]);

  if (screen === "exam" && test) {
    const active = currentParts.find((part) => Number(part.number) === activePart) || currentParts[0];
    const activePassageTitle = active ? resolvedPassageTitle(active) : "";
    const activeQuestionMeta = active?.groups
      .map((group) => {
        const question = group.questions.find((item) => controlQuestionId(group, item) === activeQuestionId);
        if (!question) return null;
        return controlQuestion(group, question).display_number ?? question.number;
      })
      .find((value) => value != null);
    const dockQuestions = currentParts.flatMap((part) =>
      part.groups.flatMap((group) =>
        group.questions.map((question) => ({
          part,
          group,
          question,
          controlId: sharedQuestionIds(group)[0] || String(question.id)
        }))
      )
    );
    const currentDockIndex = dockQuestions.findIndex((item) => item.controlId === activeQuestionId);
    const moveDock = (direction: -1 | 1) => {
      const fallbackIndex = dockQuestions.findIndex((item) => Number(item.part.number) === activePart);
      const baseIndex = currentDockIndex >= 0 ? currentDockIndex : fallbackIndex;
      const target = dockQuestions[Math.max(0, Math.min(dockQuestions.length - 1, baseIndex + direction))];
      if (target) scrollToQuestion(target.controlId, Number(target.part.number));
    };
    const readingStyle = {
      "--reading-font-size": `${readingFontSize}px`
    } as CSSProperties;
    return (
      <div
        className="exam-workbench"
        role="application"
        aria-label="IELTS阅读考试工作台"
        data-test-id={test.id}
        data-test-title={test.title}
        data-part-number={active?.number}
        style={readingStyle}
      >
        <header className="exam-topbar">
          <div>
            <span className="exam-kicker">{modeLabel(mode)}</span>
            <strong>{test.title}</strong>
          </div>
          <div className="exam-progress"><span>已答</span><strong>{answeredCount}/{questionRows.length}</strong></div>
          <div className={remainingSeconds !== null && remainingSeconds <= 300 ? "exam-timer warning" : "exam-timer"}>
            <span>{remainingSeconds === null ? "已用时间" : "剩余时间"}</span>
            <strong>{formatSeconds(remainingSeconds ?? elapsedSeconds)}</strong>
          </div>
          <div className="exam-question-timer">
            <span>本题 {activeQuestionMeta ? `Q${activeQuestionMeta}` : ""}</span>
            <strong>{formatSeconds(questionElapsedSeconds[activeQuestionId] || 0)}</strong>
          </div>
          <button type="button" className="exam-ghost-button exam-utility-button" onClick={() => setPaused(true)}>暂停</button>
          <button type="button" className="exam-ghost-button exam-utility-button exam-help-button" onClick={() => setShowHelp(true)}>帮助</button>
          <div className="exam-font-controls" role="group" aria-label="阅读字号">
            <button
              type="button"
              disabled={readingFontSize === READING_FONT_SIZES[0]}
              onClick={() => changeReadingFontSize(-1)}
              aria-label="减小阅读字号"
            >A−</button>
            <output aria-live="polite">{readingFontSize}</output>
            <button
              type="button"
              disabled={readingFontSize === READING_FONT_SIZES[READING_FONT_SIZES.length - 1]}
              onClick={() => changeReadingFontSize(1)}
              aria-label="增大阅读字号"
            >A+</button>
          </div>
          <button type="button" className="exam-ghost-button" disabled={!hasDraftProgress} onClick={saveDraftManually}>保存草稿</button>
          <button type="button" className="exam-ghost-button" onClick={leaveExam}>退出</button>
          <button
            type="button"
            className="exam-submit-button"
            disabled={submitting}
            onClick={() => {
              if (window.confirm(`确定交卷吗？当前已完成 ${answeredCount}/${questionRows.length} 题。`)) {
                void submitCurrent(false);
              }
            }}
          >{submitting ? "正在判分…" : "交卷"}</button>
        </header>
        {notice ? <div className="exam-notice">{notice}</div> : null}
        {error ? <div className="exam-error">{error}</div> : null}
        <div className="mobile-pane-tabs" role="tablist" aria-label="切换原文和题目">
          <button
            type="button"
            role="tab"
            aria-selected={mobilePane === "passage"}
            className={mobilePane === "passage" ? "active" : ""}
            onClick={() => setMobilePane("passage")}
          >原文</button>
          <button
            type="button"
            role="tab"
            aria-selected={mobilePane === "questions"}
            className={mobilePane === "questions" ? "active" : ""}
            onClick={() => setMobilePane("questions")}
          >题目与作答 <span>{answeredCount}/{questionRows.length}</span></button>
        </div>
        {active ? (
          <div
            className="exam-grid"
            style={{
              gridTemplateColumns: `minmax(0, ${paneRatio}fr) 15px minmax(0, ${100 - paneRatio}fr)`
            }}
          >
            <section className={mobilePane === "passage" ? "passage-pane" : "passage-pane mobile-hidden"} aria-label={`Part ${active.number} 原文`}>
              <div className="pane-heading">
                <strong>Part {active.number}</strong>
                <span>阅读原文并回答第 {partQuestionRange(active)} 题</span>
              </div>
              <div className="passage-copy">
                {activePassageTitle ? <h1 className="passage-main-title">{activePassageTitle}</h1> : null}
                {active.subtitle ? <p className="passage-subtitle">{active.subtitle}</p> : null}
                {(active.paragraphs || []).map((paragraph, index, paragraphs) => {
                  const text = repairDisplayText(String(paragraph.text || "").trim());
                  if (!text) return null;
                  const key = `${paragraph.index ?? index}-${text.slice(0, 20)}`;
                  const cue = paragraph.question_cue;
                  const isSectionLetter = /^[A-Z]$/.test(text) && !paragraph.label;
                  const isLabelled = Boolean(paragraph.label && /^[A-Z]$/.test(paragraph.label.trim()));
                  const isCategory = looksLikePassageCategory(text);
                  const listing = passageListingParts(text);
                  const isLegend = /^(?:[A-Z]\s+for\s+\w+\s*){2,}/i.test(text);
                  const isHeading = Boolean(cue) || looksLikePassageHeading(text, index, paragraphs);
                  const cueRange = cue ? (cue.start === cue.end ? String(cue.start) : `${cue.start}–${cue.end}`) : "";
                  return (
                    <Fragment key={key}>
                      {cue ? (
                        <div className="passage-question-cue" role="note">
                          <strong>Questions {cueRange}</strong>
                          <span>Read the text below and answer Questions {cueRange}.</span>
                        </div>
                      ) : null}
                      {paragraph.table ? (
                        <PassageTable paragraph={paragraph} />
                      ) : isSectionLetter ? (
                        <div className="passage-section-letter passage-unit">{text}</div>
                      ) : isLabelled ? (
                        <div className="passage-paragraph passage-labelled"><strong>{paragraph.label}</strong><p className="passage-unit">{text}</p></div>
                      ) : isCategory ? (
                        <h2 className="passage-category-heading passage-unit">{text}</h2>
                      ) : listing ? (
                        <p className="passage-listing passage-unit"><strong>{listing.label}</strong><span>{listing.detail}</span></p>
                      ) : isLegend ? (
                        <p className="passage-legend passage-unit">{text}</p>
                      ) : isHeading ? (
                        <h2 className="passage-subheading passage-unit">{text}</h2>
                      ) : (
                        <p className={/^[-•]/.test(text) ? "passage-paragraph passage-bullet passage-unit" : "passage-paragraph passage-unit"}>{text}</p>
                      )}
                    </Fragment>
                  );
                })}
              </div>
            </section>
            <div
              className="exam-divider"
              role="separator"
              aria-label="拖动调整文章与题目宽度"
              aria-valuemin={30}
              aria-valuemax={70}
              aria-valuenow={Math.round(paneRatio)}
              tabIndex={0}
              onPointerDown={beginDividerDrag}
              onKeyDown={adjustDividerFromKeyboard}
            />
            <section
              className={mobilePane === "questions" ? "questions-pane" : "questions-pane mobile-hidden"}
              aria-label={`Part ${active.number} 题目`}
              onPointerDownCapture={(event) => {
                const element = (event.target as Element).closest<HTMLElement>('[id^="question-"]');
                if (element) setActiveQuestionId(element.id.slice("question-".length));
              }}
              onFocusCapture={(event) => {
                const element = (event.target as Element).closest<HTMLElement>('[id^="question-"]');
                if (element) setActiveQuestionId(element.id.slice("question-".length));
              }}
            >
              <div className="pane-heading questions-pane-heading question-annotation-unit">
                <strong>Questions {partQuestionRange(active)}</strong>
                <span>请完成本 Part 的全部题目</span>
              </div>
              <div className="questions-scroll">
                {active.groups.map((group, groupIndex) => (
                  <QuestionGroupControl
                    key={group.id || `${active.number}-${groupIndex}`}
                    group={group}
                    answers={answers}
                    flagged={flagged}
                    onAnswer={updateAnswer}
                    onFlag={toggleFlag}
                  />
                ))}
              </div>
            </section>
          </div>
        ) : null}
        <nav className="exam-question-dock" aria-label="题目导航">
          <div className="dock-section-strip" role="tablist" aria-label="选择Section和题目">
            {currentParts.map((part) => {
              const partRows = part.groups.flatMap((group) =>
                group.questions.map((question) => ({ group, question }))
              );
              const completed = partRows.filter(({ group, question }) =>
                answerIsComplete(group, answers[String(question.id)])
              ).length;
              const isActivePart = Number(part.number) === activePart;
              return (
                <section className={`dock-section${isActivePart ? " active" : ""}`} key={part.number}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isActivePart}
                    className="dock-section-label"
                    onClick={() => {
                      setActivePart(Number(part.number));
                      setActiveQuestionId(firstQuestionId(part));
                      setMobilePane("passage");
                    }}
                  >
                    <strong>{isActivePart ? `P${part.number}` : `Passage ${part.number}`}</strong>
                    {!isActivePart ? <span>{completed} of {partRows.length}</span> : null}
                  </button>
                  {isActivePart ? (
                    <div className="dock-question-list">
                      {partRows.map(({ group, question }) => {
                        const id = String(question.id);
                        const controlId = sharedQuestionIds(group)[0] || id;
                        const answered = answerIsComplete(group, answers[id]);
                        const className = [
                          answered ? "answered" : "",
                          flagged[id] ? "flagged" : "",
                          activeQuestionId === controlId ? "current" : ""
                        ].filter(Boolean).join(" ");
                        return (
                          <button
                            type="button"
                            key={id}
                            className={className}
                            onClick={() => scrollToQuestion(controlId, Number(part.number))}
                            aria-label={`第${questionNumber(question)}题${answered ? "，已作答" : ""}${flagged[id] ? "，已标记" : ""}`}
                          >{questionNumber(question)}</button>
                        );
                      })}
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
          <div className="dock-step-buttons" aria-label="上一题或下一题">
            <button
              type="button"
              onClick={() => moveDock(-1)}
              disabled={currentDockIndex <= 0}
              aria-label="上一题"
            >←</button>
            <button
              type="button"
              onClick={() => moveDock(1)}
              disabled={currentDockIndex >= dockQuestions.length - 1}
              aria-label="下一题"
            >→</button>
          </div>
        </nav>
        {paused ? (
          <div className="exam-pause-overlay" role="dialog" aria-modal="true">
            <div><span>PAUSED</span><h2>练习已暂停</h2><p>计时已经冻结。答案不会自动保存，需要时请手动保存草稿。</p>
              <button className="primary-button" type="button" onClick={() => setPaused(false)}>继续作答</button>
              <button className="secondary-button" type="button" disabled={!hasDraftProgress} onClick={saveDraftAndLeave}>保存草稿并退出</button>
            </div>
          </div>
        ) : null}
        {showHelp ? (
          <div className="system-modal-backdrop">
            <section className="system-modal exam-help-modal" role="dialog" aria-modal="true">
              <header><h2>机考帮助</h2><button type="button" onClick={() => setShowHelp(false)}>关闭</button></header>
              <ul><li>拖动中间分隔线可在 30%–70% 范围调整文章宽度。</li><li>暂停会冻结计时，不会清空答案。</li><li>答案不会自动保存；点击“保存草稿”后，才可从“管理草稿”继续。</li><li>普通退出或从题卡再次开始都会创建空白练习。</li></ul>
            </section>
          </div>
        ) : null}
      </div>
    );
  }

  if (screen === "result" && result) {
    return (
      <div className="page-wrap result-page">
        <div className="result-hero">
          <div>
            <p className="eyebrow">SERVER-SCORED RESULT</p>
            <h1>{result.test_title}</h1>
            <p>标准答案、证据和解析仅在服务端交卷后返回。</p>
          </div>
          <div className="result-score"><strong>{result.score}/{result.total}</strong><span>{result.accuracy}%</span></div>
          {result.band_estimate?.eligible ? (
            <div className="result-band"><span>预计 GT Band</span><strong>{result.band_estimate.display_band}</strong><small>练习参考，并非官方成绩</small></div>
          ) : null}
        </div>
        <section className="result-metrics">
          <article><span>用时</span><strong>{formatSeconds(result.total_elapsed_seconds)}</strong></article>
          <article><span>未作答</span><strong>{result.unanswered_count}</strong></article>
          <article><span>错题</span><strong>{result.wrong_questions.length}</strong></article>
          <article><span>模式</span><strong>{result.total === 40 ? "整套" : "Part"}</strong></article>
        </section>
        <section className="result-section">
          <h2>Part表现</h2>
          <div className="part-result-grid">
            {result.part_results.map((part) => (
              <article key={part.part_number}><span>Part {part.part_number}</span><strong>{part.score}/{part.total}</strong><small>{part.accuracy}% · {formatSeconds(part.elapsed_seconds || 0)}</small></article>
            ))}
          </div>
        </section>
        <section className="result-section">
          <h2>错题复盘</h2>
          {result.wrong_questions.length ? (
            <div className="wrong-result-list">
              {result.wrong_questions.map((question) => (
                <article className="wrong-result-card" key={question.id}>
                  <div><span>Q{question.number} · {question.question_type} · 用时 {formatSeconds(question.elapsed_seconds || 0)}</span><strong>{displayMarkup(question.prompt)}</strong></div>
                  <div className="answer-comparison"><span>你的答案：{question.user_answer || "未作答"}</span><span>正确答案：{question.correct_answer}</span></div>
                  {question.answer_error_type === "word_limit_exceeded" ? <p className="result-warning">答案超过题目词数限制。</p> : null}
                  {question.analysis || question.reason ? <p>{question.analysis || question.reason}</p> : null}
                  {question.paraphrasing ? <p><b>同义替换：</b>{question.paraphrasing}</p> : null}
                  {question.evidence?.length ? <blockquote>{question.evidence.join("\n")}</blockquote> : null}
                </article>
              ))}
            </div>
          ) : <div className="perfect-result">全部答对，本次没有错题。</div>}
        </section>
        <div className="result-actions">
          <button type="button" className="secondary-button" onClick={() => { setScreen("library"); setResult(null); }}>返回题库</button>
          {result.test_id ? <button type="button" className="primary-button" onClick={() => void startExam(result.test_id, result.total === 40 ? "mock_exam" : "part_practice", result.total === 40 ? [] : result.part_numbers)}>再做一次</button> : null}
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrap practice-library-page">
      <header className="page-heading practice-heading">
        <p className="eyebrow">QUESTION BANK & EXAM</p>
        <h1>题库与考试工作台</h1>
        <p>58套真实G类阅读题库。完整模考从 Part 1 开始，60分钟连续完成40题，过程不显示答案、解析或AI提示；整套学习与单Part训练可从题卡直接进入。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="practice-stat-strip">
        <article><span>完整套题</span><strong>{tests.length || 58}</strong></article>
        <article><span>总题量</span><strong>2,320</strong></article>
        <article><span>真实判分对照</span><strong>174/174</strong></article>
        <article><span>完整模考</span><strong>60分钟</strong></article>
      </section>
      <section className="difficulty-toolbar" aria-label="按相对难度筛选">
        <div><strong>题库内相对难度</strong><span>依据文章和题型结构计算，不是剑桥官方难度</span></div>
        <div>{(["all", "easy", "medium", "hard"] as const).map((value) => (
          <button key={value} type="button" className={difficulty === value ? `active ${value}` : value} onClick={() => setDifficulty(value)}>
            {value === "all" ? "全部" : value === "easy" ? "简单" : value === "medium" ? "中等" : "困难"}
            <small>{value === "all" ? tests.length : tests.filter((item) => item.difficulty?.level === value).length}</small>
          </button>
        ))}</div>
        <button type="button" className="secondary-button draft-manager-button" onClick={() => {
          setShowDrafts(true);
          refreshDrafts();
        }}>管理草稿（{drafts.length}）</button>
      </section>
      <div className="library-layout">
        <section className="book-library" aria-label="题库列表">
          {loading ? <div className="library-loading">正在加载题库…</div> : groupedTests.map(([bookNumber, items]) => (
            <section className="book-section" key={bookNumber}>
              <div className="book-section-heading"><div><span>CAMBRIDGE IELTS</span><h2>剑雅 {bookNumber}</h2></div><small>{items.length} 套 · 每套40题</small></div>
              <div className="test-card-grid">
                {items.map((item) => (
                  <article className="test-card" key={item.id}>
                    <div><span>{item.name}</span><strong>{item.title}</strong><small>3 Parts · 40 Questions</small><em className={`difficulty-badge ${item.difficulty?.level || "medium"}`}>{item.difficulty?.label || "中等"} · {item.difficulty?.caption || "相对难度"}</em></div>
                    <div className="test-actions">
                      <button type="button" className="primary-button" onClick={() => void startExam(item.id, "mock_exam", [])}>60分钟模考</button>
                      <button type="button" className="secondary-button" onClick={() => void startExam(item.id, "study", [])}>整套学习</button>
                    </div>
                    <div className="part-action-row">
                      {[1, 2, 3].map((part) => <button type="button" key={part} onClick={() => void startExam(item.id, "part_practice", [part])}>Part {part}</button>)}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </section>
        <aside className="recent-sessions">
          <div className="recent-heading"><span>RECENT</span><h2>最近练习</h2></div>
          {history.length ? history.slice(0, 12).map((session) => (
            <button type="button" className="session-card" key={session.session_id} onClick={() => void openHistory(session.session_id)}>
              <span>{formatDate(session.created_at)}</span>
              <strong>{session.test_title}</strong>
              <small>{session.score}/{session.total} · {session.accuracy}%{session.estimated_band != null ? ` · Band ${session.estimated_band.toFixed(1)}` : ""}</small>
            </button>
          )) : <div className="empty-history">完成一次练习后，成绩会保存在这里。</div>}
        </aside>
      </div>
      {showDrafts ? (
        <div className="system-modal-backdrop" onMouseDown={() => setShowDrafts(false)}>
          <section className="system-modal draft-manager" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><span>LOCAL DRAFTS</span><h2>草稿管理器</h2></div><button type="button" onClick={() => setShowDrafts(false)}>关闭</button></header>
            {drafts.length ? <div>{drafts.map((draft) => (
              <article key={draft.key}><div><strong>{draft.testTitle || draft.testId}</strong><span>{draft.mode || "练习"} · Part {(draft.partNumbers || []).join(",") || "1–3"} · 已答 {Object.keys(draft.answers || {}).length} 题</span><small>{draft.updatedAt ? formatDate(draft.updatedAt) : "旧草稿"}</small></div>
                <div className="draft-actions">
                  <button className="primary-button" type="button" onClick={() => {
                    setShowDrafts(false);
                    void startExam(draft.testId, draft.mode || "study", draft.partNumbers || [], true, draft);
                  }}>继续草稿</button>
                  <button className="secondary-button danger-text" type="button" onClick={() => {
                    if (window.confirm("确定清除这份本机草稿吗？此操作无法撤销。")) {
                      localStorage.removeItem(draft.key);
                      setDrafts((current) => current.filter((item) => item.key !== draft.key));
                    }
                  }}>清除</button>
                </div>
              </article>
            ))}</div> : <p>当前没有未提交草稿。</p>}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function answerIsPresent(value: AnswerValue | undefined): boolean {
  return Array.isArray(value) ? value.length > 0 : Boolean(String(value || "").trim());
}

function answerIsComplete(group: PublicQuestionGroup, value: AnswerValue | undefined): boolean {
  if (!Array.isArray(value)) return Boolean(String(value || "").trim());
  const subtype = group.question_subtype || group.question_type;
  const requiredChoices = Number(
    group.required_choices
      || (group.shared_response ? sharedQuestionIds(group).length : 1)
  );
  return subtype === "multiple_choice_multiple" || requiredChoices > 1
    ? value.length >= requiredChoices
    : value.length > 0;
}

function optionDisplayText(option: QuestionOption): string {
  const text = repairDisplayText(String(option.text || "")).trim();
  if (!text || text.localeCompare(option.code, undefined, { sensitivity: "accent" }) === 0) return "";
  const escapedCode = option.code.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(`^${escapedCode}[.):\\s-]+`, "i"), "").trim();
}

function repairDisplayText(value: string): string {
  return value
    .replace(/^lt(?=\s)/, "It")
    .replace(/([.!?])(?=[A-Z][a-z])/g, "$1 ");
}

function displayMarkup(value: string) {
  return repairDisplayText(String(value || ""))
    .split(/(<b>.*?<\/b>)/gi)
    .filter(Boolean)
    .map((part, index) => {
      const bold = part.match(/^<b>(.*?)<\/b>$/i);
      const copy = (bold?.[1] || part).replace(/<[^>]+>/g, "");
      return bold
        ? <strong key={`markup-${index}`}>{copy}</strong>
        : <Fragment key={`markup-${index}`}>{copy}</Fragment>;
    });
}

function QuestionGroupControl({
  group,
  answers,
  flagged,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const subtype = group.question_subtype || group.question_type;
  const matching = subtype.startsWith("matching_");
  const firstQuestion = group.questions[0];
  const groupOptions = firstQuestion ? optionsFor(group, firstQuestion) : [];
  const matchingHasDescriptions = matching && groupOptions.some((option) => Boolean(optionDisplayText(option)));
  const useMatchingMatrix = matching && groupOptions.length > 0 && !matchingHasDescriptions && !group.shared_response;
  const structuredCompletion = ["table_completion", "flow_chart_completion", "summary_completion", "note_completion", "sentence_completion", "diagram_label_completion", "short_answer"]
    .includes(subtype) && Boolean(group.content_template || group.table?.rows?.length || group.table?.content?.length);

  return (
    <section className={`question-group question-group--${matching ? "matching" : subtype}`}>
      <QuestionInstructions group={group} />

      {structuredCompletion ? (
        <StructuredCompletionGroup
          group={group}
          answers={answers}
          flagged={flagged}
          onAnswer={onAnswer}
          onFlag={onFlag}
        />
      ) : useMatchingMatrix ? (
        <div className="matching-matrix-wrap" role="region" aria-label={`${group.question_label || "匹配题"}答题表`} tabIndex={0}>
          <table className="matching-answer-matrix">
            <thead>
              <tr>
                <th scope="col">题目</th>
                {groupOptions.map((option) => <th scope="col" key={option.code}>{option.code}</th>)}
                <th scope="col">标记</th>
              </tr>
            </thead>
            <tbody>
              {group.questions.map((question) => {
                const id = String(question.id);
                const value = answers[id];
                return (
                  <tr
                    key={id}
                    id={`question-${id}`}
                    className={`${answerIsPresent(value) ? "answered" : ""}${flagged[id] ? " flagged" : ""}`}
                  >
                    <th scope="row">
                      <span className="matrix-question-number">{questionNumber(question)}</span>
                      <span className="question-annotation-unit">{displayMarkup(question.prompt)}</span>
                    </th>
                    {groupOptions.map((option) => (
                      <td key={option.code}>
                        <label className="matrix-answer-radio">
                          <input
                            type="radio"
                            name={`answer-${id}`}
                            checked={value === option.code}
                            onChange={() => onAnswer(id, option.code)}
                          />
                          <span aria-hidden="true" />
                          <span className="sr-only">第{questionNumber(question)}题选择 {option.code}</span>
                        </label>
                      </td>
                    ))}
                    <td>
                      <div className="matrix-row-tools">
                        <button type="button" className={flagged[id] ? "flag-button active" : "flag-button"} onClick={() => onFlag(id)}>
                          {flagged[id] ? "已标" : "标记"}
                        </button>
                        {answerIsPresent(value) ? <button type="button" className="clear-answer" onClick={() => onAnswer(id, "")}>清除</button> : null}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="matching-scroll-hint">选项较多时可左右滑动查看。</p>
        </div>
      ) : matchingHasDescriptions ? (
        <MatchingTextGroup
          group={group}
          options={groupOptions}
          answers={answers}
          flagged={flagged}
          onAnswer={onAnswer}
          onFlag={onFlag}
        />
      ) : (
        (group.shared_response ? group.questions.slice(0, 1) : group.questions).map((question) => {
          const sharedIds = sharedQuestionIds(group);
          const answerIds = sharedIds.length ? sharedIds : [String(question.id)];
          return (
            <QuestionControl
              key={question.id}
              group={group}
              question={controlQuestion(group, question)}
              value={answers[answerIds[0]]}
              flagged={answerIds.some((questionId) => Boolean(flagged[questionId]))}
              onChange={(value) => onAnswer(answerIds, value)}
              onFlag={() => onFlag(answerIds)}
            />
          );
        })
      )}
    </section>
  );
}

function MatchingTextGroup({
  group,
  options,
  answers,
  flagged,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  options: QuestionOption[];
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const [selectedCode, setSelectedCode] = useState("");
  const optionReuse = /may (?:be )?used .*more than once|may use .*more than once/i.test(group.instructions || "");
  const optionMap = new Map(options.map((option) => [option.code, option]));
  const usedCodes = new Set(
    group.questions
      .map((question) => String(answers[String(question.id)] || ""))
      .filter(Boolean)
  );

  function assignAnswer(questionId: string, code: string) {
    if (!code) return;
    if (!optionReuse) {
      const occupied = group.questions.find((question) =>
        String(question.id) !== questionId && String(answers[String(question.id)] || "") === code
      );
      if (occupied) onAnswer(String(occupied.id), "");
    }
    onAnswer(questionId, code);
    setSelectedCode("");
  }

  function dropAnswer(event: ReactDragEvent<HTMLDivElement>, questionId: string) {
    event.preventDefault();
    assignAnswer(questionId, event.dataTransfer.getData("text/plain"));
  }

  return (
    <div className="matching-text-group">
      <p className="matching-text-help">
        先选择一个选项，再点击题目右侧答案框；桌面端也可拖动选项字母到答案框。
        {optionReuse ? " 本题选项可以重复使用。" : ""}
      </p>
      <div className="matching-interactive-bank" role="listbox" aria-label="匹配选项">
        <strong>选项</strong>
        <div>
          {options.map((option) => {
            const selected = selectedCode === option.code;
            const used = !optionReuse && usedCodes.has(option.code);
            return (
              <div
                className={`matching-option-card${selected ? " selected" : ""}${used ? " used" : ""}`}
                key={option.code}
                role="option"
                tabIndex={0}
                draggable
                aria-selected={selected}
                onDragStart={(event) => {
                  event.dataTransfer.effectAllowed = optionReuse ? "copy" : "move";
                  event.dataTransfer.setData("text/plain", option.code);
                }}
                onClick={() => {
                  if (window.getSelection()?.toString()) return;
                  setSelectedCode((current) => current === option.code ? "" : option.code);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  setSelectedCode((current) => current === option.code ? "" : option.code);
                }}
              >
                <strong>{option.code}</strong>
                <span className="question-annotation-unit">{optionDisplayText(option)}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="matching-question-list">
        {group.questions.map((question) => {
          const id = String(question.id);
          const code = String(answers[id] || "");
          const chosen = optionMap.get(code);
          return (
            <article
              className={`matching-question-row${code ? " answered" : ""}${flagged[id] ? " flagged" : ""}`}
              id={`question-${id}`}
              key={id}
            >
              <div className="matching-question-copy">
                <span className="question-number">{questionNumber(question)}</span>
                <p className="question-annotation-unit">{displayMarkup(question.prompt)}</p>
              </div>
              <div className="matching-answer-cell">
                <div
                  className={`matching-answer-slot${chosen ? " filled" : ""}${selectedCode ? " ready" : ""}`}
                  onClick={() => selectedCode && assignAnswer(id, selectedCode)}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => dropAnswer(event, id)}
                >
                  <input
                    value={code}
                    placeholder={`${questionNumber(question)} 拖拽或输入选项字母`}
                    autoComplete="off"
                    spellCheck={false}
                    aria-label={`第${questionNumber(question)}题答案框`}
                    onChange={(event) => {
                      const nextCode = event.target.value.trim().toUpperCase();
                      if (!nextCode) onAnswer(id, "");
                      else if (optionMap.has(nextCode)) assignAnswer(id, nextCode);
                    }}
                  />
                  {chosen ? <span className="sr-only">{optionDisplayText(chosen)}</span> : null}
                </div>
                {chosen ? (
                  <button type="button" className="matching-answer-clear" onClick={() => onAnswer(id, "")} aria-label={`清除第${questionNumber(question)}题答案`}>×</button>
                ) : null}
              </div>
              <button type="button" className={flagged[id] ? "flag-button active" : "flag-button"} onClick={() => onFlag(id)}>
                {flagged[id] ? "取消标记" : "标记此题"}
              </button>
            </article>
          );
        })}
      </div>
    </div>
  );
}

function StructuredTemplate({
  text,
  questions,
  answers,
  flagged,
  onAnswer,
  onFlag
}: {
  text: string;
  questions: Map<string, PublicQuestion>;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  return (
    <>
      {String(text || "").split(/(\$[^$]+\$)/g).map((part, index) => {
        const match = part.match(/^\$([^$]+)\$$/);
        if (!match) return <span key={`copy-${index}`}>{displayMarkup(part)}</span>;
        const id = match[1];
        const question = questions.get(id);
        if (!question) return <span key={`missing-${id}-${index}`}>_____</span>;
        const value = answers[id];
        return (
          <span
            className={`inline-answer-wrap${flagged[id] ? " flagged" : ""}${answerIsPresent(value) ? " answered" : ""}`}
            id={`question-${id}`}
            key={`answer-${id}-${index}`}
          >
            <label>
              <span className="inline-answer-number">{questionNumber(question)}</span>
              <input
                value={typeof value === "string" ? value : ""}
                onChange={(event) => onAnswer(id, event.target.value)}
                autoComplete="off"
                spellCheck={false}
                aria-label={`第${questionNumber(question)}题答案`}
              />
            </label>
            {answerIsPresent(value) ? (
              <button type="button" className="inline-answer-tool clear" onClick={() => onAnswer(id, "")} aria-label={`清除第${questionNumber(question)}题答案`}>×</button>
            ) : null}
            <button type="button" className="inline-answer-tool flag" onClick={() => onFlag(id)} aria-label={`${flagged[id] ? "取消" : ""}标记第${questionNumber(question)}题`}>⚑</button>
          </span>
        );
      })}
    </>
  );
}

function StructuredCompletionGroup({
  group,
  answers,
  flagged,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const subtype = group.question_subtype || group.question_type;
  const questions = new Map(group.questions.map((question) => [String(question.id), question]));
  const rows = group.table?.rows?.length ? group.table.rows : group.table?.content || [];
  const templateProps = { questions, answers, flagged, onAnswer, onFlag };
  const diagramSource = group.image_url
    ? group.image_url.replace(/^\/static\/media\//, "/media/")
    : "";

  if (subtype === "table_completion" && rows.length) {
    return (
      <div className="structured-completion table-completion-layout">
        {group.table?.title ? <h3 className="question-annotation-unit">{group.table.title}</h3> : null}
        <div className="completion-table-scroll">
          <table>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`row-${rowIndex}`}>
                  {row.map((cell, cellIndex) => {
                    const Cell = rowIndex === 0 ? "th" : "td";
                    return <Cell className="question-annotation-unit" key={`cell-${cellIndex}`}><StructuredTemplate text={cell} {...templateProps} /></Cell>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className={`structured-completion ${subtype}-layout`}>
      {diagramSource ? <img src={diagramSource} alt="题目示意图" className="completion-diagram" /> : null}
      <div className="inline-gap-block question-annotation-unit">
        <StructuredTemplate text={group.content_template || ""} {...templateProps} />
      </div>
    </div>
  );
}

function QuestionControl({
  group,
  question,
  value,
  flagged,
  onChange,
  onFlag
}: {
  group: PublicQuestionGroup;
  question: PublicQuestion;
  value: AnswerValue | undefined;
  flagged: boolean;
  onChange: (value: AnswerValue) => void;
  onFlag: () => void;
}) {
  const subtype = group.question_subtype || group.question_type;
  const options = optionsFor(group, question);
  const id = String(question.id);
  const number = questionNumber(question);
  const judgement = subtype === "true_false_not_given"
    ? ["TRUE", "FALSE", "NOT GIVEN"]
    : subtype === "yes_no_not_given"
      ? ["YES", "NO", "NOT GIVEN"]
      : null;
  const requiredChoices = Number(
    group.required_choices
      || (group.shared_response ? sharedQuestionIds(group).length : 1)
  );
  const multi = subtype === "multiple_choice_multiple" || requiredChoices > 1;
  const matching = subtype.startsWith("matching_");
  const family = judgement ? "judgement" : multi ? "multiple" : subtype === "multiple_choice_single" ? "choice" : matching ? "matching" : "completion";
  const inlineCompletion = family === "completion" && options.length === 0;
  const hasAnswer = answerIsPresent(value);
  const answered = answerIsComplete(group, value);
  const prompt = repairDisplayText(question.prompt);
  const promptGap = prompt.match(/_{3,}/);
  const promptBeforeGap = promptGap ? prompt.slice(0, promptGap.index) : prompt;
  const promptAfterGap = promptGap ? prompt.slice((promptGap.index || 0) + promptGap[0].length) : "";

  return (
    <article className={`question-card question-card--${family}${flagged ? " flagged" : ""}${answered ? " answered" : ""}`} id={`question-${id}`}>
      <div className="question-title-row">
        <span className="question-number">{number}</span>
        <p className="question-annotation-unit">
          {inlineCompletion ? (
            <label className="inline-question-answer">
              <span>{promptBeforeGap}</span>
              <input
                value={typeof value === "string" ? value : ""}
                onChange={(event) => onChange(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                aria-label={`第 ${number} 题答案`}
              />
              {promptAfterGap ? <span>{promptAfterGap}</span> : null}
            </label>
          ) : displayMarkup(prompt)}
        </p>
        <div className="question-tools">
          {hasAnswer ? <button type="button" className="clear-answer" onClick={() => onChange(multi ? [] : "")}>清除答案</button> : null}
          <button type="button" className={flagged ? "flag-button active" : "flag-button"} onClick={onFlag}>{flagged ? "取消标记" : "标记此题"}</button>
        </div>
      </div>
      {judgement ? (
        <div className="answer-options judgement-options">
          {judgement.map((option) => (
            <label key={option} className={value === option ? "selected" : ""}>
              <input type="radio" name={`answer-${id}`} value={option} checked={value === option} onChange={() => onChange(option)} />
              <span className="answer-control-mark radio-mark" aria-hidden="true" />
              <span className="answer-option-copy question-annotation-unit">{option}</span>
            </label>
          ))}
        </div>
      ) : multi && options.length ? (
        <>
          <div className="multi-choice-status">
            请选择 {requiredChoices || 2} 个答案
            <span>已选 {Array.isArray(value) ? value.length : 0}/{requiredChoices || 2}</span>
          </div>
          <div className="answer-options multi-options">
            {options.map((option) => {
              const selected = Array.isArray(value) && value.includes(option.code);
              return (
                <label key={option.code} className={selected ? "selected" : ""}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => {
                      const current = Array.isArray(value) ? value : [];
                      if (selected) onChange(current.filter((item) => item !== option.code));
                      else if (current.length < (requiredChoices || 2)) onChange([...current, option.code]);
                    }}
                  />
                  <span className="answer-control-mark checkbox-mark" aria-hidden="true" />
                  <span className="answer-option-copy question-annotation-unit"><b>{option.code}</b>{optionDisplayText(option)}</span>
                </label>
              );
            })}
          </div>
        </>
      ) : options.length && !matching && subtype === "multiple_choice_single" ? (
        <div className="answer-options choice-options">
          {options.map((option) => (
            <label key={option.code} className={value === option.code ? "selected" : ""}>
              <input type="radio" name={`answer-${id}`} checked={value === option.code} onChange={() => onChange(option.code)} />
              <span className="answer-control-mark radio-mark" aria-hidden="true" />
              <span className="answer-option-copy question-annotation-unit"><b>{option.code}</b>{optionDisplayText(option)}</span>
            </label>
          ))}
        </div>
      ) : options.length ? (
        <label className={matching ? "select-answer matching-select-answer" : "select-answer"}>
          <span>{matching ? "匹配" : "选择答案"}</span>
          <select value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}>
            <option value="">请选择</option>
            {options.map((option) => <option key={option.code} value={option.code}>{option.code}{optionDisplayText(option) ? ` · ${optionDisplayText(option)}` : ""}</option>)}
          </select>
        </label>
      ) : null}
    </article>
  );
}
