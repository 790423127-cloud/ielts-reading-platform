"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import {
  fetchPublicTest,
  fetchSession,
  fetchSessions,
  fetchTests,
  sessionReportDownloadUrl,
  submitSession,
  type PublicPart,
  type PublicQuestion,
  type PublicQuestionGroup,
  type PublicTest,
  type QuestionResult,
  type QuestionOption,
  type ScoringResult,
  type SessionSummary,
  type TestIndexItem
} from "@/lib/api";
import {
  beginReadingAttempt,
  readAnnotationsForSubmission,
  READING_ANNOTATIONS_EVENT,
  type ReadingAnnotation,
  type ReadingAttemptDetail
} from "@/lib/readingAnnotations";

type ExamMode = "mock_exam" | "study" | "part_practice";
type Screen = "library" | "exam" | "result";
type AnswerValue = string | string[];
type ResultQuestionFilter = "all" | "wrong" | "correct" | "unanswered";

type DraftState = {
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  annotations?: ReadingAnnotation[];
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
const PANE_RATIO_STORAGE_KEY = "ielts-exam-pane-ratio-v4";

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
  if (!sourceTitle || GENERIC_PASSAGE_TITLE.test(sourceTitle)) return "";

  const normalizedSourceTitle = normalizedPassageTitle(sourceTitle);
  const sourceTitleAppearsInBody = (part.paragraphs || []).some(
    (paragraph) => normalizedPassageTitle(paragraph.text) === normalizedSourceTitle
  );
  return sourceTitleAppearsInBody ? "" : sourceTitle;
}

function structuredTemplateParts(text: string, questions: Map<string, PublicQuestion>): string[] {
  const questionIds = [...questions.keys()];
  if (!questionIds.length) return [String(text || "")];

  const escapedIds = questionIds
    .sort((left, right) => right.length - left.length)
    .map((id) => id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const questionPlaceholder = new RegExp(`(\\$(?:${escapedIds.join("|")})\\$)`, "g");
  return String(text || "").split(questionPlaceholder);
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

type PassageParagraph = NonNullable<PublicPart["paragraphs"]>[number];
type PassageSection = {
  cue?: PassageParagraph["question_cue"];
  paragraphs: PassageParagraph[];
};

function splitPassageSections(part: PublicPart): PassageSection[] {
  const sections: PassageSection[] = [{ paragraphs: [] }];
  for (const paragraph of part.paragraphs || []) {
    if (paragraph.question_cue) {
      sections.push({ cue: paragraph.question_cue, paragraphs: [paragraph] });
      continue;
    }
    sections[sections.length - 1].paragraphs.push(paragraph);
  }
  return sections.filter((section) => section.paragraphs.length > 0);
}

function isPassageDocumentHeading(text: string): boolean {
  const value = text.trim();
  const letters = value.replace(/[^A-Za-z]/g, "");
  return value.length <= 96 && letters.length >= 4 && value === value.toUpperCase();
}

function passageSectionHasDocumentFrame(section: PassageSection): boolean {
  const texts = section.paragraphs.map((paragraph) => String(paragraph.text || "").trim());
  const bulletCount = texts.filter((text) => /^(?:•|-)\s+/.test(text)).length;
  const headingCount = texts.filter(isPassageDocumentHeading).length;
  return bulletCount >= 3 && headingCount >= 1;
}

function PassageRichText({ text }: { text: string }) {
  return text.split(/(\bInterExchange\b)/g).filter(Boolean).map((part, index) =>
    part === "InterExchange"
      ? <strong className="passage-brand" key={`brand-${index}`}>{part}</strong>
      : <Fragment key={`copy-${index}`}>{part}</Fragment>
  );
}

function PassageParagraphBlock({
  paragraph,
  index,
  documentFrame
}: {
  paragraph: PassageParagraph;
  index: number;
  documentFrame: boolean;
}) {
  const text = repairDisplayText(String(paragraph.text || "").trim());
  if (!text) return null;
  if (paragraph.table) return <PassageTable paragraph={paragraph} />;

  const isSectionLetter = /^[A-Z]$/.test(text) && !paragraph.label;
  const isLabelled = Boolean(paragraph.label && /^[A-Z]$/.test(paragraph.label.trim()));
  const isCategory = looksLikePassageCategory(text);
  const listing = passageListingParts(text);
  const isLegend = /^(?:[A-Z]\s+for\s+\w+\s*){2,}/i.test(text);
  const isDocumentHeading = documentFrame && isPassageDocumentHeading(text);
  const isDocumentIntro = documentFrame && index === 0 && text.includes("?");
  const isDocumentEmphasis = documentFrame
    && /^(?:Only\b.*!|Call\b|Sign up\b)/i.test(text);
  const isBullet = /^(?:•|-)\s+/.test(text);
  const content = <PassageRichText text={text} />;

  if (isSectionLetter) return <div className="passage-section-letter passage-unit">{content}</div>;
  if (isLabelled) {
    return (
      <div className="passage-paragraph passage-labelled">
        <strong>{paragraph.label}</strong>
        <p className="passage-unit">{content}</p>
      </div>
    );
  }
  if (isDocumentHeading) return <h2 className="passage-document-heading passage-unit">{content}</h2>;
  if (isDocumentIntro) return <p className="passage-document-intro passage-unit">{content}</p>;
  if (isDocumentEmphasis) return <p className="passage-document-emphasis passage-unit">{content}</p>;
  if (isCategory) return <h2 className="passage-category-heading passage-unit">{content}</h2>;
  if (listing) {
    return (
      <p className="passage-listing passage-unit">
        <strong>{listing.label}</strong>
        <span><PassageRichText text={listing.detail} /></span>
      </p>
    );
  }
  if (isLegend) return <p className="passage-legend passage-unit">{content}</p>;
  return (
    <p className={isBullet ? "passage-paragraph passage-bullet passage-unit" : "passage-paragraph passage-unit"}>
      {content}
    </p>
  );
}

function PassageTable({ paragraph }: { paragraph: NonNullable<PublicPart["paragraphs"]>[number] }) {
  const table = paragraph.table;
  if (!table) return null;
  const columnCount = Math.max(1, table.headers.length, ...table.rows.map((row) => row.length));
  const hasMergedHeading = Boolean(
    table.headers[0]?.trim()
    && table.headers.length > 1
    && table.headers.slice(1).every((header) => !header.trim())
  );
  const tableClassName = columnCount >= 5
    ? "passage-source-table passage-source-table--wide passage-unit"
    : "passage-source-table passage-unit";
  const renderHeaders = () => (
    <tr>
      {hasMergedHeading ? (
        <th className="passage-source-table-group-heading" colSpan={columnCount} scope="colgroup">
          {table.headers[0]}
        </th>
      ) : table.headers.map((header, index) => (
        <th scope="col" key={`passage-table-header-${index}`}>{header}</th>
      ))}
    </tr>
  );
  return (
    <div className={tableClassName}>
      <table>
        {table.caption ? <caption>{table.caption}</caption> : null}
        {table.intro ? (
          <thead>
            <tr><td colSpan={columnCount}>{table.intro}</td></tr>
            {renderHeaders()}
          </thead>
        ) : (
          <thead>{renderHeaders()}</thead>
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

function PassageContent({ part }: { part: PublicPart }) {
  const passageTitle = resolvedPassageTitle(part);
  const sections = splitPassageSections(part);
  return (
    <div className="passage-copy">
      {part.subtitle ? <p className="passage-subtitle">{part.subtitle}</p> : null}
      {sections.map((section, sectionIndex) => {
        const cue = section.cue;
        const cueRange = cue
          ? (cue.start === cue.end ? String(cue.start) : `${cue.start}–${cue.end}`)
          : "";
        const documentFrame = passageSectionHasDocumentFrame(section);
        return (
          <Fragment key={`passage-section-${sectionIndex}`}>
            {cue ? (
              <div className="passage-question-cue" role="note">
                <strong>Questions {cueRange}</strong>
                <span>Read the text below and answer Questions {cueRange}.</span>
              </div>
            ) : null}
            <div className={documentFrame ? "passage-section passage-section--document" : "passage-section"}>
              {sectionIndex === 0 && passageTitle
                ? <h1 className="passage-main-title">{passageTitle}</h1>
                : null}
              {section.paragraphs.map((paragraph, paragraphIndex) => (
                <PassageParagraphBlock
                  documentFrame={documentFrame}
                  index={paragraphIndex}
                  key={`${paragraph.index ?? paragraphIndex}-${String(paragraph.text || "").slice(0, 20)}`}
                  paragraph={paragraph}
                />
              ))}
            </div>
          </Fragment>
        );
      })}
    </div>
  );
}

const INSTRUCTION_EMPHASIS = /\b(NO MORE THAN(?:\s+[A-Z]+){0,5}|ONE WORD ONLY|TRUE|FALSE|NOT GIVEN|YES|NO|A NUMBER)\b/g;
const INSTRUCTION_EMPHASIS_EXACT = /^(?:NO MORE THAN(?:\s+[A-Z]+){0,5}|ONE WORD ONLY|TRUE|FALSE|NOT GIVEN|YES|NO|A NUMBER)$/;
const INSTRUCTION_ACTION_LINE = /^(?:Choose|Write|In boxes?|Read each|Complete|Answer|Select|Match|Label|Fill|Use|Drag|TRUE|FALSE|NOT GIVEN|YES|NO)\b/i;

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
        {details.map((line, index) => (
          <p className={INSTRUCTION_ACTION_LINE.test(line) ? "instruction-action-line" : undefined} key={`${line}-${index}`}>
            <InstructionLine>{line}</InstructionLine>
          </p>
        ))}
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

function reviewValueText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return repairDisplayText(String(value)).trim();
  if (Array.isArray(value)) return value.map(reviewValueText).filter(Boolean).join("；");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const text = reviewValueText(item);
        return text ? `${key}：${text}` : "";
      })
      .filter(Boolean)
      .join("；");
  }
  return String(value);
}

function reviewOptionText(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") return repairDisplayText(String(value)).trim();
  if (!value || typeof value !== "object") return "";
  const option = value as Record<string, unknown>;
  const code = reviewValueText(option.code ?? option.label ?? option.value);
  const text = reviewValueText(option.text ?? option.content ?? option.title);
  if (!text) return code;
  return code && text !== code ? `${code}. ${text}` : text;
}

function questionReviewStatus(question: QuestionResult): ResultQuestionFilter {
  if (!String(question.user_answer || "").trim()) return "unanswered";
  return question.is_correct ? "correct" : "wrong";
}

function historicalAnswerValue(question: QuestionResult): AnswerValue {
  const value = String(question.user_answer || "").trim();
  if (question.question_subtype === "multiple_choice_multiple") {
    return value.split(/\s*,\s*/).filter(Boolean);
  }
  return value;
}

function reviewAnswerTokens(value: string | undefined): string[] {
  return String(value || "")
    .split(/\s*[,;|]\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function answerReviewClass(option: string, results: QuestionResult[]): string {
  const wrongResults = results.filter((result) => !result.is_correct);
  const correctAnswers = new Set(wrongResults.flatMap((result) => reviewAnswerTokens(result.correct_answer)));
  const userAnswers = new Set(wrongResults.flatMap((result) => reviewAnswerTokens(result.user_answer)));
  if (correctAnswers.has(option)) return " review-correct-option";
  if (userAnswers.has(option)) return " review-user-wrong-option";
  return "";
}

function InlineAnswerReview({ question }: { question: QuestionResult | undefined }) {
  if (!question || question.is_correct) return null;
  const unanswered = questionReviewStatus(question) === "unanswered";
  return (
    <span className={`inline-answer-review${unanswered ? " unanswered" : " wrong"}`}>
      <span>{unanswered ? "未作答" : <>你的答案 <b>{question.user_answer}</b></>}</span>
      <strong>正确答案 <b>{question.correct_answer || "题库暂未提供"}</b></strong>
    </span>
  );
}

function ResultQuestionCard({ question }: { question: QuestionResult }) {
  const status = questionReviewStatus(question);
  const statusLabel = status === "correct" ? "回答正确" : status === "unanswered" ? "未作答" : "回答错误";
  const explanation = reviewValueText(question.analysis || question.reason);
  const location = reviewValueText(question.location_analysis);
  const paraphrasing = reviewValueText(question.paraphrasing);
  const keywords = reviewValueText(question.keywords);
  const wrongReasons = reviewValueText(question.wrong_reasons);
  const options = (question.options || []).map(reviewOptionText).filter(Boolean);

  return (
    <details className={`result-question-card ${status}`} open={status !== "correct"}>
      <summary>
        <span className="result-question-number">Q{question.number}</span>
        <span className={`result-status-badge ${status}`}>{statusLabel}</span>
        <span className="result-question-meta">Part {question.part_number} · {question.question_type} · 用时 {formatSeconds(question.elapsed_seconds || 0)}</span>
        <strong className="result-question-prompt">{displayMarkup(question.prompt)}</strong>
        <span className="result-detail-toggle">查看完整解析</span>
      </summary>
      <div className="result-question-body">
        {question.instructions ? (
          <section className="result-explanation-block instruction">
            <span>题目要求</span>
            <p>{displayMarkup(question.instructions)}</p>
          </section>
        ) : null}
        {options.length ? (
          <section className="result-explanation-block">
            <span>原题选项</span>
            <ol className="result-option-list">
              {options.map((option, index) => <li key={`${question.id}-option-${index}`}>{option}</li>)}
            </ol>
          </section>
        ) : null}
        <div className="answer-comparison">
          <article><span>你的答案</span><strong>{question.user_answer || "未作答"}</strong></article>
          <article><span>正确答案</span><strong>{question.correct_answer || "题库暂未提供"}</strong></article>
        </div>
        {question.answer_error_type === "word_limit_exceeded" ? <p className="result-warning">答案超过题目规定的词数限制。</p> : null}
        <div className="result-analysis-grid">
          {explanation ? <section className="result-explanation-block"><span>答案解析</span><p>{explanation}</p></section> : null}
          {location ? <section className="result-explanation-block"><span>定位分析</span><p>{location}</p></section> : null}
          {paraphrasing ? <section className="result-explanation-block"><span>同义替换</span><p>{paraphrasing}</p></section> : null}
          {keywords ? <section className="result-explanation-block"><span>关键词</span><p>{keywords}</p></section> : null}
          {wrongReasons ? <section className="result-explanation-block"><span>易错原因</span><p>{wrongReasons}</p></section> : null}
        </div>
        {question.evidence?.length ? (
          <blockquote className="result-evidence">
            <strong>原文定位句</strong>
            {question.evidence.map((item, index) => <p key={`${question.id}-evidence-${index}`}>{item}</p>)}
          </blockquote>
        ) : (
          <p className="result-evidence-missing">本题源数据暂未提供可核验的定位句；报告不会猜测或伪造证据。</p>
        )}
      </div>
    </details>
  );
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
  const [resultSessionId, setResultSessionId] = useState("");
  const [resultQuestionFilter, setResultQuestionFilter] = useState<ResultQuestionFilter>("all");
  const [resultPartFilter, setResultPartFilter] = useState<number | "all">("all");
  const [resultSourcePart, setResultSourcePart] = useState<number | null>(null);
  const [resultAnnotationsOpen, setResultAnnotationsOpen] = useState(false);
  const [historyEntrySource, setHistoryEntrySource] = useState(false);
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
  const [paneRatio, setPaneRatio] = useState(45);
  const [annotationCount, setAnnotationCount] = useState(0);
  const timedOutRef = useRef(false);
  const activePartRef = useRef(1);
  const activeQuestionIdRef = useRef("");
  const activeQuestionLockUntilRef = useRef(0);
  const draftSnapshotRef = useRef<DraftState | null>(null);
  const initialHistorySessionRef = useRef(false);

  useEffect(() => {
    activeQuestionIdRef.current = activeQuestionId;
  }, [activeQuestionId]);

  useEffect(() => {
    activePartRef.current = activePart;
  }, [activePart]);

  useEffect(() => {
    function onAnnotations(event: Event) {
      const detail = (event as CustomEvent<ReadingAttemptDetail>).detail;
      if (!detail) return;
      setAnnotationCount(detail.annotations.length);
    }
    window.addEventListener(READING_ANNOTATIONS_EVENT, onAnnotations);
    return () => window.removeEventListener(READING_ANNOTATIONS_EVENT, onAnnotations);
  }, []);

  useEffect(() => {
    setReadingFontSize(normalizeReadingFontSize(window.localStorage.getItem("ielts-passage-font-size")));
    const storedRatioValue = window.localStorage.getItem(PANE_RATIO_STORAGE_KEY);
    if (storedRatioValue !== null && storedRatioValue.trim() !== "") {
      const storedRatio = Number(storedRatioValue);
      if (Number.isFinite(storedRatio)) setPaneRatio(Math.max(30, Math.min(70, storedRatio)));
    }
    refreshDrafts();
  }, []);

  useEffect(() => {
    if (initialHistorySessionRef.current) return;
    const sessionId = new URLSearchParams(window.location.search).get("session");
    if (!sessionId) return;
    initialHistorySessionRef.current = true;
    void openHistory(sessionId, true);
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
        const hasAnnotations = Array.isArray(value.annotations) && value.annotations.length > 0;
        if (!hasAnswers && !hasFlags && !hasAnnotations) continue;
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
  const hasDraftProgress = answeredCount > 0 || Object.values(flagged).some(Boolean) || annotationCount > 0;

  draftSnapshotRef.current = screen === "exam" && draftKey && clientSubmissionId ? {
    answers,
    flagged,
    annotations: test ? readAnnotationsForSubmission(test.id, partNumbers) : [],
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
    const snapshot = draftSnapshotRef.current;
    if (!snapshot) return null;
    const draft: DraftState = {
      ...snapshot,
      annotations: test ? readAnnotationsForSubmission(test.id, partNumbers) : []
    };
    const hasAnswers = Object.values(draft.answers).some(answerIsPresent);
    const hasFlags = Object.values(draft.flagged).some(Boolean);
    const hasAnnotations = Boolean(draft.annotations?.length);
    if (!hasAnswers && !hasFlags && !hasAnnotations) return null;
    window.localStorage.setItem(draftKey, JSON.stringify(draft));
    return draft;
  }, [clientSubmissionId, draftKey, partNumbers, screen, test]);

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
        timed_out: timedOut,
        annotations: readAnnotationsForSubmission(test.id, partNumbers)
      });
      setResult(response.result);
      setResultAnnotationsOpen(false);
      setResultSessionId(response.session_id);
      setHistoryEntrySource(false);
      setResultQuestionFilter(response.result.wrong_questions.length ? "wrong" : "all");
      setResultPartFilter("all");
      setResultSourcePart(Number(response.result.wrong_questions[0]?.part_number || response.result.part_results[0]?.part_number || 1));
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
      const nextSubmissionId = draft?.clientSubmissionId || newSubmissionId();
      setClientSubmissionId(nextSubmissionId);
      beginReadingAttempt({
        attemptId: nextSubmissionId,
        testId: loaded.id,
        testTitle: loaded.title,
        annotations: draft?.annotations || []
      });
      setDraftKey(key);
      setResult(null);
      setResultSessionId("");
      setHistoryEntrySource(false);
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

  async function openHistory(sessionId: string, fromHistoryCenter = false) {
    setLoading(true);
    setError("");
    try {
      const session = await fetchSession(sessionId, USER_ID);
      let sourceTest: PublicTest | null = null;
      try {
        sourceTest = await fetchPublicTest(session.result.test_id);
      } catch {
        // The score report remains available even if the public passage cannot be reloaded.
      }
      setResult(session.result);
      setResultAnnotationsOpen(false);
      setResultSessionId(sessionId);
      setHistoryEntrySource(fromHistoryCenter);
      setResultQuestionFilter(session.result.wrong_questions.length ? "wrong" : "all");
      setResultPartFilter("all");
      setResultSourcePart(Number(session.result.wrong_questions[0]?.part_number || session.result.part_results[0]?.part_number || 1));
      setTest(sourceTest);
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
        <div className="exam-partbar">
          <strong>Part {active.number}</strong>
          <span>Read the text below and answer questions {partQuestionRange(active)}</span>
        </div>
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
              gridTemplateColumns: `minmax(0, ${paneRatio}fr) 8px minmax(0, ${100 - paneRatio}fr)`
            }}
          >
            <section className={mobilePane === "passage" ? "passage-pane" : "passage-pane mobile-hidden"} aria-label={`Part ${active.number} 原文`}>
              <div className="pane-heading">
                <strong>Part {active.number}</strong>
                <span>阅读原文并回答第 {partQuestionRange(active)} 题</span>
              </div>
              <PassageContent part={active} />
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
    const questionResults = result.question_results || [];
    const correctCount = questionResults.filter((question) => question.is_correct).length;
    const unansweredCount = questionResults.filter((question) => questionReviewStatus(question) === "unanswered").length;
    const answeredWrongCount = questionResults.filter((question) => questionReviewStatus(question) === "wrong").length;
    const resultAnnotations = result.annotations || [];
    const noteCount = resultAnnotations.filter((annotation) => Boolean(annotation.note?.trim())).length;
    const highlightCount = resultAnnotations.filter((annotation) => annotation.kind === "highlight").length;
    const typeResults = result.type_results?.length ? result.type_results : (() => {
      const buckets = new Map<string, { type: string; correct: number; total: number; accuracy: number }>();
      for (const question of questionResults) {
        const type = question.question_type || "其他";
        const bucket = buckets.get(type) || { type, correct: 0, total: 0, accuracy: 0 };
        bucket.total += 1;
        if (question.is_correct) bucket.correct += 1;
        bucket.accuracy = Math.round((bucket.correct / bucket.total) * 1000) / 10;
        buckets.set(type, bucket);
      }
      return [...buckets.values()].sort((left, right) => left.accuracy - right.accuracy || right.total - left.total);
    })();
    const filteredQuestions = questionResults.filter((question) => {
      const statusMatches = resultQuestionFilter === "all"
        || (resultQuestionFilter === "wrong" ? !question.is_correct : questionReviewStatus(question) === resultQuestionFilter);
      const partMatches = resultPartFilter === "all" || Number(question.part_number) === resultPartFilter;
      return statusMatches && partMatches;
    });
    const questionsByPart = filteredQuestions.reduce((groups, question) => {
      const part = Number(question.part_number) || 0;
      const rows = groups.get(part) || [];
      rows.push(question);
      groups.set(part, rows);
      return groups;
    }, new Map<number, QuestionResult[]>());
    const submittedPartNumbers = new Set(result.part_results.map((part) => Number(part.part_number)));
    const reviewParts = test?.id === result.test_id
      ? test.parts.filter((part) => submittedPartNumbers.has(Number(part.number)))
      : [];
    const firstReviewPart = Number(result.wrong_questions[0]?.part_number || reviewParts[0]?.number || 0);
    const activeReviewPart = reviewParts.find((part) => Number(part.number) === Number(resultSourcePart || firstReviewPart))
      || reviewParts[0];
    const activeReviewQuestions = activeReviewPart
      ? questionResults.filter((question) => Number(question.part_number) === Number(activeReviewPart.number))
      : [];
    const activeReviewQuestionResults = new Map(
      activeReviewQuestions.map((question) => [String(question.id), question])
    );
    const activeHistoricalAnswers = Object.fromEntries(
      activeReviewQuestions.map((question) => [String(question.id), historicalAnswerValue(question)])
    );

    return (
      <div className="page-wrap result-page">
        <nav className="result-report-nav" aria-label="报告目录">
          <a href="#result-overview">总览</a>
          <a href="#result-source-review">原文与作答</a>
          <a href="#result-performance">分项表现</a>
          <a href="#result-review">逐题复盘</a>
          {resultAnnotations.length ? (
            <a href="#result-annotations" onClick={() => setResultAnnotationsOpen(true)}>高亮与笔记</a>
          ) : null}
        </nav>
        <div className="result-hero" id="result-overview">
          <div>
            <p className="eyebrow">DETAILED SCORE REPORT</p>
            <h1>{result.test_title}</h1>
            <p>交卷后详细报告 · 标准答案、题库解析与原文证据仅在服务端判分后显示。</p>
          </div>
          <div className="result-score"><strong>{result.score}/{result.total}</strong><span>{result.accuracy}%</span></div>
          {result.band_estimate?.eligible ? (
            <div className="result-band"><span>预计 GT Band</span><strong>{result.band_estimate.display_band}</strong><small>练习参考，并非官方成绩</small></div>
          ) : null}
        </div>
        <section className="result-metrics">
          <article><span>用时</span><strong>{formatSeconds(result.total_elapsed_seconds)}</strong></article>
          <article className="correct"><span>答对</span><strong>{correctCount}</strong></article>
          <article className="wrong"><span>答错</span><strong>{answeredWrongCount}</strong></article>
          <article className="unanswered"><span>未作答</span><strong>{unansweredCount}</strong></article>
          <article><span>模式</span><strong>{result.total === 40 ? "整套" : "Part"}</strong></article>
          <article><span>高亮 / 笔记</span><strong>{highlightCount} / {noteCount}</strong></article>
        </section>
        <section className={`result-priority-summary ${result.wrong_questions.length ? "has-wrong" : "perfect"}`}>
          <div>
            <span>{result.wrong_questions.length ? "优先复盘" : "本次结果"}</span>
            <strong>{result.wrong_questions.length ? `${result.wrong_questions.length} 道题需要复盘` : "全部答对"}</strong>
            <p>{result.wrong_questions.length ? "下方已默认只显示错题和未作答题，并展开你的答案与正确答案对比。" : "可以在逐题复盘中展开查看全部题目的答案依据。"}</p>
          </div>
          <a href="#result-review" onClick={() => setResultQuestionFilter(result.wrong_questions.length ? "wrong" : "all")}>
            {result.wrong_questions.length ? "立即查看错题" : "查看全部题目"}
          </a>
        </section>
        <section className="result-section result-source-review" id="result-source-review">
          <header className="result-section-heading">
            <div><span>SOURCE REVIEW</span><h2>原文与我的作答记录</h2></div>
            <p>按 Part 恢复考试时的原文，右侧逐题对照你提交的答案和正确答案；包含错题的 Part 默认展开。</p>
          </header>
          {activeReviewPart ? (
            <div className="result-source-workbench">
              <nav className="exam-question-dock result-source-part-dock" aria-label="切换报告 Part">
                <div className="dock-section-strip" role="tablist" aria-label="切换报告 Part 和题目">
                  {reviewParts.map((part) => {
                    const partQuestions = questionResults.filter((question) => Number(question.part_number) === Number(part.number));
                    const partResult = result.part_results.find((item) => Number(item.part_number) === Number(part.number));
                    const active = Number(part.number) === Number(activeReviewPart.number);
                    return (
                      <section className={`dock-section result-source-dock-section${active ? " active" : ""}`} key={part.number}>
                        <button
                          type="button"
                          role="tab"
                          className="dock-section-label result-source-dock-label"
                          aria-selected={active}
                          onClick={() => setResultSourcePart(Number(part.number))}
                        >
                          <strong>{active ? `P${part.number}` : `Passage ${part.number}`}</strong>
                          {!active ? <span>{partResult?.score || 0} of {partQuestions.length}</span> : null}
                        </button>
                        {active ? (
                          <div className="dock-question-list result-source-dock-questions" aria-label={`Part ${part.number} 题号`}>
                            {partQuestions.map((question) => {
                              const status = questionReviewStatus(question);
                              return (
                                <button
                                  type="button"
                                  className={status}
                                  key={`source-dock-${question.id}`}
                                  onClick={() => document.getElementById(`question-${question.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}
                                  aria-label={`第${question.number}题，${status === "correct" ? "正确" : status === "unanswered" ? "未作答" : "错误"}`}
                                >{question.number}</button>
                              );
                            })}
                          </div>
                        ) : null}
                      </section>
                    );
                  })}
                </div>
              </nav>
              <header className="result-source-active-heading">
                <div><strong>Part {activeReviewPart.number}</strong><span>{resolvedPassageTitle(activeReviewPart) || activeReviewPart.title}</span></div>
                <em>{activeReviewQuestions.length} 题 · {activeReviewQuestions.filter((question) => !question.is_correct).length} 题需复盘</em>
              </header>
              <div className="result-source-split">
                <section className="result-source-passage" aria-label={`Part ${activeReviewPart.number} 原文`}>
                  <header><strong>原文</strong><span>阅读题库原始内容</span></header>
                  <div className="result-source-scroll"><PassageContent part={activeReviewPart} /></div>
                </section>
                <section className="result-source-answers" aria-label={`Part ${activeReviewPart.number} 作答记录`}>
                  <header><strong>我的作答记录</strong><span>按原做题界面只读还原</span></header>
                  <div className="result-source-scroll result-source-exam-view">
                    {activeReviewPart.groups.map((group, groupIndex) => {
                      const groupResults = group.questions
                        .map((question) => activeReviewQuestionResults.get(String(question.id)))
                        .filter((question): question is QuestionResult => Boolean(question));
                      if (!groupResults.length) return null;
                      return (
                        <section className="result-source-question-group" key={group.id || `review-${activeReviewPart.number}-${groupIndex}`}>
                          <fieldset disabled>
                            <QuestionGroupControl
                              group={group}
                              answers={activeHistoricalAnswers}
                              flagged={{}}
                              reviewResults={activeReviewQuestionResults}
                              onAnswer={() => undefined}
                              onFlag={() => undefined}
                            />
                          </fieldset>
                        </section>
                      );
                    })}
                  </div>
                </section>
              </div>
            </div>
          ) : (
            <div className="result-source-unavailable">
              <strong>本次成绩和逐题答案仍可正常查看。</strong>
              <p>原文暂时未能从题库重新载入，请返回练习记录后再次打开本条记录。</p>
            </div>
          )}
        </section>
        <section className="result-section result-performance-section" id="result-performance">
          <header className="result-section-heading"><div><span>PERFORMANCE</span><h2>分项表现</h2></div><p>先看 Part，再看题型，快速找到失分集中点。</p></header>
          <h3>Part 表现</h3>
          <div className="part-result-grid">
            {result.part_results.map((part) => (
              <article key={part.part_number}>
                <span>Part {part.part_number}</span>
                <strong>{part.score}/{part.total}</strong>
                <small>{part.accuracy}% · {formatSeconds(part.elapsed_seconds || 0)}</small>
                <div className="result-progress" aria-label={`Part ${part.part_number} 正确率 ${part.accuracy}%`}><i style={{ width: `${Math.min(100, Math.max(0, part.accuracy))}%` }} /></div>
              </article>
            ))}
          </div>
          <h3 className="result-type-title">题型表现</h3>
          <div className="result-type-table-wrap">
            <table className="result-type-table">
              <thead><tr><th>题型</th><th>答对</th><th>总题数</th><th>正确率</th><th>表现</th></tr></thead>
              <tbody>{typeResults.map((item) => (
                <tr key={item.type}>
                  <td><strong>{item.type}</strong></td>
                  <td>{item.correct}</td>
                  <td>{item.total}</td>
                  <td>{item.accuracy}%</td>
                  <td><div className="result-progress"><i style={{ width: `${Math.min(100, Math.max(0, item.accuracy))}%` }} /></div></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
        <section className="result-section result-review-section" id="result-review">
          <header className="result-section-heading">
            <div><span>QUESTION REVIEW</span><h2>逐题复盘</h2></div>
            <p>完整保留原题、你的答案、正确答案、解析、定位、同义替换和证据句。</p>
          </header>
          <div className="result-review-toolbar">
            <div className="result-filter-group" aria-label="按作答结果筛选">
              {([
                ["all", "全部题目", questionResults.length],
                ["wrong", "错题", result.wrong_questions.length],
                ["unanswered", "未作答", unansweredCount],
                ["correct", "答对", correctCount]
              ] as const).map(([value, label, count]) => (
                <button type="button" className={resultQuestionFilter === value ? "active" : ""} key={value} onClick={() => setResultQuestionFilter(value)}>
                  {label}<small>{count}</small>
                </button>
              ))}
            </div>
            <div className="result-filter-group part-filter" aria-label="按Part筛选">
              <button type="button" className={resultPartFilter === "all" ? "active" : ""} onClick={() => setResultPartFilter("all")}>全部 Part</button>
              {result.part_results.map((part) => (
                <button type="button" className={resultPartFilter === part.part_number ? "active" : ""} key={part.part_number} onClick={() => setResultPartFilter(part.part_number)}>Part {part.part_number}</button>
              ))}
            </div>
          </div>
          <p className="result-review-count">当前显示 {filteredQuestions.length} / {questionResults.length} 题。错题与未作答题默认展开；答对题可按需展开。</p>
          {filteredQuestions.length ? (
            <div className="result-question-groups">
              {[...questionsByPart.entries()].sort(([left], [right]) => left - right).map(([partNumber, questions]) => (
                <section className="result-part-review" key={partNumber}>
                  <header><h3>Part {partNumber}</h3><span>{questions.length} 题</span></header>
                  <div className="result-question-list">
                    {questions.map((question) => <ResultQuestionCard question={question} key={question.id} />)}
                  </div>
                </section>
              ))}
            </div>
          ) : <div className="perfect-result">当前筛选条件下没有题目。</div>}
        </section>
        {resultAnnotations.length ? (
          <section
            className={`result-section result-annotations${resultAnnotationsOpen ? " is-open" : " is-collapsed"}`}
            id="result-annotations"
          >
            <header className="result-section-heading">
              <div><span>MY NOTES</span><h2>我的高亮与笔记</h2></div>
              <div className="result-annotations-heading-actions">
                <p>只显示本次已提交并随练习记录保存的标注。</p>
                <button
                  type="button"
                  className="result-section-toggle"
                  aria-expanded={resultAnnotationsOpen}
                  aria-controls="result-annotation-content"
                  onClick={() => setResultAnnotationsOpen((open) => !open)}
                >
                  {resultAnnotationsOpen ? "收起" : `展开（${resultAnnotations.length}）`}
                </button>
              </div>
            </header>
            {resultAnnotationsOpen ? (
              <div className="result-annotation-list" id="result-annotation-content">
                {resultAnnotations.map((annotation) => (
                  <article key={annotation.id}>
                    <div><span>Part {annotation.partNumber}</span><em>{annotation.highlightLevel === "secondary" ? "二次高亮" : annotation.note ? "笔记" : "高亮"}</em></div>
                    <blockquote>{annotation.selectedText}</blockquote>
                    {annotation.note ? <p>{annotation.note}</p> : null}
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        ) : null}
        <div className="result-actions">
          <button type="button" className="secondary-button" onClick={() => {
            if (historyEntrySource) {
              window.location.assign("/history");
              return;
            }
            setScreen("library");
            setResult(null);
          }}>{historyEntrySource ? "返回练习记录" : "返回题库"}</button>
          {resultSessionId ? <a className="primary-button" href={sessionReportDownloadUrl(resultSessionId, "pdf")}>下载正式 PDF</a> : null}
          {resultSessionId ? <a className="secondary-button" href={sessionReportDownloadUrl(resultSessionId, "docx")}>下载 DOCX</a> : null}
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
              <article key={draft.key}><div><strong>{draft.testTitle || draft.testId}</strong><span>{draft.mode || "练习"} · Part {(draft.partNumbers || []).join(",") || "1–3"} · 已答 {Object.keys(draft.answers || {}).length} 题 · 标注 {draft.annotations?.length || 0} 条</span><small>{draft.updatedAt ? formatDate(draft.updatedAt) : "旧草稿"}</small></div>
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
  return value.replace(/([.!?])(?=[A-Z][a-z])/g, "$1 ");
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
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
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
          reviewResults={reviewResults}
          onAnswer={onAnswer}
          onFlag={onFlag}
        />
      ) : useMatchingMatrix ? (
        <div className="matching-matrix-wrap" role="region" aria-label={`${group.question_label || "匹配题"}答题表`} tabIndex={0}>
          <table className="matching-answer-matrix">
            <thead>
              <tr>
                <th scope="col"><span className="sr-only">题目</span></th>
                {groupOptions.map((option) => <th scope="col" key={option.code}>{option.code}</th>)}
              </tr>
            </thead>
            <tbody>
              {group.questions.map((question) => {
                const id = String(question.id);
                const value = answers[id];
                const reviewResult = reviewResults?.get(id);
                const reviewStatus = reviewResult && !reviewResult.is_correct
                  ? questionReviewStatus(reviewResult)
                  : "";
                return (
                  <tr
                    key={id}
                    id={`question-${id}`}
                    className={`${answerIsPresent(value) ? "answered" : ""}${flagged[id] ? " flagged" : ""}${reviewStatus ? ` review-${reviewStatus}` : ""}`}
                  >
                    <th scope="row">
                      <span className="matrix-question-number">{questionNumber(question)}</span>
                      <span className="question-annotation-unit">{displayMarkup(question.prompt)}</span>
                      <InlineAnswerReview question={reviewResult} />
                      <span className="matrix-row-tools">
                        <button type="button" className={flagged[id] ? "flag-button active" : "flag-button"} onClick={() => onFlag(id)}>
                          {flagged[id] ? "已标" : "标记"}
                        </button>
                        {answerIsPresent(value) ? <button type="button" className="clear-answer" onClick={() => onAnswer(id, "")}>清除</button> : null}
                      </span>
                    </th>
                    {groupOptions.map((option) => (
                      <td
                        className={reviewResult && !reviewResult.is_correct
                          ? answerReviewClass(option.code, [reviewResult]).trim()
                          : ""}
                        key={option.code}
                      >
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
          reviewResults={reviewResults}
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
              reviewResults={answerIds
                .map((questionId) => reviewResults?.get(questionId))
                .filter((result): result is QuestionResult => Boolean(result))}
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
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  options: QuestionOption[];
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
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
          const chosenText = chosen ? optionDisplayText(chosen) : "";
          const reviewResult = reviewResults?.get(id);
          const reviewStatus = reviewResult && !reviewResult.is_correct
            ? questionReviewStatus(reviewResult)
            : "";
          return (
            <article
              className={`matching-question-row${code ? " answered" : ""}${flagged[id] ? " flagged" : ""}${reviewStatus ? ` review-${reviewStatus}` : ""}`}
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
                    aria-label={`第${questionNumber(question)}题答案框${chosenText ? `，已选择 ${code} ${chosenText}` : ""}`}
                    onFocus={(event) => {
                      if (chosen) event.currentTarget.select();
                    }}
                    onChange={(event) => {
                      const nextCode = event.target.value.trim().toUpperCase();
                      if (!nextCode) onAnswer(id, "");
                      else if (optionMap.has(nextCode)) assignAnswer(id, nextCode);
                    }}
                  />
                  {chosenText ? <span className="matching-answer-description">· {chosenText}</span> : null}
                </div>
                {chosen ? (
                  <button type="button" className="matching-answer-clear" onClick={() => onAnswer(id, "")} aria-label={`清除第${questionNumber(question)}题答案`}>×</button>
                ) : null}
              </div>
              <InlineAnswerReview question={reviewResult} />
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
  reviewResults,
  onAnswer,
  onFlag
}: {
  text: string;
  questions: Map<string, PublicQuestion>;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  return (
    <>
      {structuredTemplateParts(text, questions).map((part, index) => {
        const match = part.match(/^\$([^$]+)\$$/);
        if (!match) return <span key={`copy-${index}`}>{displayMarkup(part)}</span>;
        const id = match[1];
        const question = questions.get(id);
        if (!question) return <span key={`missing-${id}-${index}`}>_____</span>;
        const value = answers[id];
        return (
          <Fragment key={`answer-${id}-${index}`}>
            <span
              className={`inline-answer-wrap${flagged[id] ? " flagged" : ""}${answerIsPresent(value) ? " answered" : ""}`}
              id={`question-${id}`}
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
            <InlineAnswerReview question={reviewResults?.get(id)} />
          </Fragment>
        );
      })}
    </>
  );
}

function StructuredCompletionGroup({
  group,
  answers,
  flagged,
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const subtype = group.question_subtype || group.question_type;
  const questions = new Map(group.questions.map((question) => [String(question.id), question]));
  const rows = group.table?.rows?.length ? group.table.rows : group.table?.content || [];
  const templateProps = { questions, answers, flagged, reviewResults, onAnswer, onFlag };
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
  reviewResults = [],
  onChange,
  onFlag
}: {
  group: PublicQuestionGroup;
  question: PublicQuestion;
  value: AnswerValue | undefined;
  flagged: boolean;
  reviewResults?: QuestionResult[];
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
            <label key={option} className={`${value === option ? "selected" : ""}${answerReviewClass(option, reviewResults)}`}>
              <input type="radio" name={`answer-${id}`} value={option} checked={value === option} onChange={() => onChange(option)} />
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
                <label key={option.code} className={`${selected ? "selected" : ""}${answerReviewClass(option.code, reviewResults)}`}>
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={() => {
                      const current = Array.isArray(value) ? value : [];
                      if (selected) onChange(current.filter((item) => item !== option.code));
                      else if (current.length < (requiredChoices || 2)) onChange([...current, option.code]);
                    }}
                  />
                  <span className="answer-option-copy question-annotation-unit"><b>{option.code}</b>{optionDisplayText(option)}</span>
                </label>
              );
            })}
          </div>
        </>
      ) : options.length && !matching && subtype === "multiple_choice_single" ? (
        <div className="answer-options choice-options">
          {options.map((option) => (
            <label key={option.code} className={`${value === option.code ? "selected" : ""}${answerReviewClass(option.code, reviewResults)}`}>
              <input type="radio" name={`answer-${id}`} checked={value === option.code} onChange={() => onChange(option.code)} />
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
      {reviewResults.some((reviewResult) => !reviewResult.is_correct) ? (
        <div className="question-inline-review-list">
          {reviewResults.map((reviewResult) => <InlineAnswerReview question={reviewResult} key={reviewResult.id} />)}
        </div>
      ) : null}
    </article>
  );
}
