"use client";

import { Fragment, createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type RefObject } from "react";
import AiTeacherPanel from "@/components/AiTeacherPanel";
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
  type SourceQuestionGroup,
  type TestIndexItem
} from "@/lib/api";
import {
  beginReadingAttempt,
  readAnnotationsForSubmission,
  READING_ANNOTATIONS_EVENT,
  type ReadingAnnotation,
  type ReadingAttemptDetail
} from "@/lib/readingAnnotations";
import { useStudyActivity } from "@/lib/useStudyActivity";

type ExamMode = "mock_exam" | "study" | "part_practice";
type Screen = "library" | "exam" | "result";
type AnswerValue = string | string[];
type QuestionReviewStatus = "wrong" | "correct" | "unanswered";

const ReviewAnalysisContext = createContext<((question: QuestionResult) => void) | null>(null);

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
const PANE_RATIO_STORAGE_KEY = "ielts-exam-pane-ratio-v6";

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

const StableHtmlDiv = memo(function StableHtmlDiv({
  className,
  html,
  contentRef,
  sourceVisualName
}: {
  className: string;
  html: string;
  contentRef?: RefObject<HTMLDivElement | null>;
  sourceVisualName?: string;
}) {
  return (
    <div
      className={className}
      data-source-visual-name={sourceVisualName}
      dangerouslySetInnerHTML={{ __html: html }}
      ref={contentRef}
    />
  );
});

const StableHtmlSpan = memo(function StableHtmlSpan({
  className,
  html
}: {
  className?: string;
  html: string;
}) {
  return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
});

function PassageDisplay({ part }: { part: PublicPart }) {
  if (part.source_html) {
    return (
      <StableHtmlDiv
        className="passage-copy passage-source-html passage-unit"
        html={part.source_html}
        sourceVisualName={part.source_visual_name}
      />
    );
  }
  return <PassageContent part={part} />;
}

function normalizedTextWithMap(value: string): { text: string; map: number[] } {
  let text = "";
  const map: number[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const raw = value[index]
      .replace(/[‘’]/g, "'")
      .replace(/[“”]/g, '"')
      .replace(/[‐‑‒–—−]/g, "-")
      .replace(/\u00a0/g, " ")
      .toLowerCase();
    if (/\s/.test(raw)) {
      if (text && !text.endsWith(" ")) {
        text += " ";
        map.push(index);
      }
      continue;
    }
    text += raw;
    map.push(index);
  }
  return { text, map };
}

function highlightEvidenceSentence(root: HTMLElement, question: QuestionResult, evidence: string): boolean {
  const needle = normalizedTextWithMap(evidence.trim()).text.trim();
  if (!needle) return false;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!node.nodeValue?.trim() || !parent || parent.closest("mark[data-answer-sentence]")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);
  for (const node of nodes) {
    const original = node.nodeValue || "";
    const normalized = normalizedTextWithMap(original);
    const normalizedStart = normalized.text.indexOf(needle);
    if (normalizedStart < 0) continue;
    const start = normalized.map[normalizedStart];
    const normalizedEnd = normalizedStart + needle.length - 1;
    const end = (normalized.map[normalizedEnd] ?? start) + 1;
    const mark = document.createElement("mark");
    mark.dataset.answerSentence = String(question.id);
    mark.className = "result-answer-sentence";
    const label = document.createElement("span");
    label.className = "result-answer-sentence-label";
    label.textContent = `[Q${question.number}]`;
    mark.append(label, document.createTextNode(original.slice(start, end)));
    const fragment = document.createDocumentFragment();
    fragment.append(document.createTextNode(original.slice(0, start)), mark, document.createTextNode(original.slice(end)));
    node.parentNode?.replaceChild(fragment, node);
    return true;
  }
  return false;
}

function appendPassageTranslations(root: HTMLElement, part: PublicPart): number {
  const candidates = [...root.querySelectorAll<HTMLElement>("p, li, td, th, h1, h2, h3, h4")];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!node.nodeValue?.trim() || !parent || parent.closest(".result-passage-translation, script, style")) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  const textCandidates: Text[] = [];
  while (walker.nextNode()) textCandidates.push(walker.currentNode as Text);
  const used = new Set<Node>();
  const unmatchedTranslations: string[] = [];
  let inserted = 0;
  for (const paragraph of part.paragraphs || []) {
    const translation = repairDisplayText(String(paragraph.translation || "")).trim();
    const source = normalizedTextWithMap(String(paragraph.text || "")).text.trim();
    if (!translation || !source) continue;
    const elementTarget = candidates
      .filter((element) => !used.has(element))
      .map((element) => ({ element, text: normalizedTextWithMap(element.textContent || "").text.trim() }))
      .filter((item) => {
        if (!item.text) return false;
        const overlaps = item.text.includes(source) || source.includes(item.text);
        const similarity = Math.min(item.text.length, source.length) / Math.max(item.text.length, source.length);
        return overlaps && similarity >= 0.72;
      })
      .sort((left, right) => left.text.length - right.text.length)[0]?.element;
    const textTarget = elementTarget ? undefined : textCandidates
      .filter((node) => !used.has(node))
      .map((node) => ({ node, text: normalizedTextWithMap(node.data).text.trim() }))
      .filter((item) => {
        if (!item.text) return false;
        const overlaps = item.text.includes(source) || source.includes(item.text);
        const similarity = Math.min(item.text.length, source.length) / Math.max(item.text.length, source.length);
        return overlaps && similarity >= 0.72;
      })
      .sort((left, right) => left.text.length - right.text.length)[0]?.node;
    if (!elementTarget && !textTarget) {
      unmatchedTranslations.push(translation);
      continue;
    }
    const translationBlock = document.createElement("span");
    translationBlock.className = "result-passage-translation";
    translationBlock.textContent = translation;
    if (elementTarget) {
      elementTarget.insertAdjacentElement("afterend", translationBlock);
      used.add(elementTarget);
    } else {
      textTarget?.parentNode?.insertBefore(translationBlock, textTarget.nextSibling);
      if (textTarget) used.add(textTarget);
    }
    inserted += 1;
  }
  if (unmatchedTranslations.length) {
    const fallback = document.createElement("section");
    fallback.className = "result-passage-translation-fallback";
    const heading = document.createElement("strong");
    heading.textContent = inserted ? "其余段落翻译" : "本 Part 中文翻译";
    fallback.append(heading);
    for (const translation of unmatchedTranslations) {
      const paragraph = document.createElement("p");
      paragraph.textContent = translation;
      fallback.append(paragraph);
    }
    root.prepend(fallback);
    inserted += unmatchedTranslations.length;
  }
  return inserted;
}

function clearPassageReviewEnhancements(root: HTMLElement) {
  root.querySelectorAll(".result-passage-translation-fallback").forEach((element) => element.remove());
  root.querySelectorAll(".result-passage-translation").forEach((element) => element.remove());
  root.querySelectorAll<HTMLElement>("mark[data-answer-sentence]").forEach((mark) => {
    mark.querySelector(".result-answer-sentence-label")?.remove();
    mark.replaceWith(...Array.from(mark.childNodes));
  });
}

function ResultPassageDisplay({
  part,
  questions,
  showTranslations
}: {
  part: PublicPart;
  questions: QuestionResult[];
  showTranslations: boolean;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    clearPassageReviewEnhancements(root);
    if (showTranslations) appendPassageTranslations(root, part);
    for (const question of questions) {
      for (const evidence of question.evidence || []) {
        if (highlightEvidenceSentence(root, question, String(evidence))) break;
      }
    }
    return () => clearPassageReviewEnhancements(root);
  }, [part, questions, showTranslations]);
  return <div className="result-passage-highlight-layer" ref={rootRef}><PassageDisplay part={part} /></div>;
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

function questionReviewStatus(question: QuestionResult): QuestionReviewStatus {
  const submittedAnswer = question.shared_response && question.credited_answer !== undefined
    ? question.credited_answer
    : question.user_answer;
  if (!String(submittedAnswer || "").trim()) return "unanswered";
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

function ResultQuestionAnalysisDialog({
  question,
  sessionId,
  onClose
}: {
  question: QuestionResult;
  sessionId: string;
  onClose: () => void;
}) {
  const status = questionReviewStatus(question);
  const explanation = reviewValueText(question.analysis || question.reason);
  const wrongReasons = reviewValueText(question.wrong_reasons);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="result-analysis-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="result-analysis-dialog" role="dialog" aria-modal="true" aria-labelledby={`result-analysis-title-${question.id}`}>
        <header>
          <div><span>QUESTION {question.number}</span><h2 id={`result-analysis-title-${question.id}`}>解析</h2></div>
          <button type="button" onClick={onClose} aria-label="关闭解析">×</button>
        </header>
        <div className="result-analysis-scroll">
          <p className="result-analysis-prompt"><b>Q{question.number}</b>{displayMarkup(question.prompt)}</p>
          <div className="result-analysis-answer-line">
            <span>正确答案：<strong>{question.correct_answer || "题库暂未提供"}</strong></span>
            <span>我的答案：<strong className={status}>{question.user_answer || "未作答"}</strong></span>
          </div>
          <section className="result-analysis-copy">
            <p><b>解题思路：</b>{explanation || "题库暂未提供解析。"}</p>
            {wrongReasons ? <p><b>避坑：</b>{wrongReasons}</p> : null}
          </section>
          {question.evidence?.length ? (
            <blockquote className="result-analysis-evidence">
              <strong>[Q{question.number}] 原文答案句</strong>
              {question.evidence.map((item, index) => <p key={`${question.id}-evidence-${index}`}>{item}</p>)}
            </blockquote>
          ) : <p className="result-evidence-missing">本题暂未提供经过核验的原文答案句，不会自动编造。</p>}
          {!question.is_correct && sessionId ? (
            <AiTeacherPanel
              key={`${sessionId}:${question.id}`}
              contextType="wrong_question"
              sessionId={sessionId}
              questionId={String(question.id)}
              title={`继续问 Q${question.number}`}
              description="AI只使用本次已交卷记录中的题干、你的答案、正确答案、解析和核验证据。"
              suggestions={["我为什么会错？", "题干和原文如何同义替换？", "正确答案的边界为什么是这样？"]}
            />
          ) : <div className="result-analysis-ai-note">本题回答正确；AI错题对话仅在错题和未作答题中提供。</div>}
        </div>
      </section>
    </div>
  );
}

function QuestionAnalysisLink({ question }: { question: QuestionResult | undefined }) {
  const onOpenAnalysis = useContext(ReviewAnalysisContext);
  if (!question || !onOpenAnalysis) return null;
  return (
    <a
      className="question-analysis-link"
      href={`#question-${question.id}`}
      role="button"
      onClick={(event) => {
        event.preventDefault();
        onOpenAnalysis(question);
      }}
      onKeyDown={(event) => {
        if (event.key !== " ") return;
        event.preventDefault();
        onOpenAnalysis(question);
      }}
      aria-label={`查看第${question.number}题解释`}
    >
      解释
    </a>
  );
}

function InlineQuestionReview({ question }: { question: QuestionResult | undefined }) {
  if (!question) return null;
  return (
    <>
      <InlineAnswerReview question={question} />
      <QuestionAnalysisLink question={question} />
    </>
  );
}

function QuestionReviewActions({ results }: { results: QuestionResult[] }) {
  if (!results.length) return null;
  const hasWrongAnswer = results.some((question) => !question.is_correct);
  return (
    <div className="question-inline-review-list">
      {hasWrongAnswer ? (
        results.some((question) => question.shared_response)
          ? <SharedMultipleAnswerReview results={results} />
          : results.map((question) => <InlineAnswerReview question={question} key={`answer-review-${question.id}`} />)
      ) : null}
      <span className="question-analysis-links" aria-label="逐题解释">
        {results.map((question) => <QuestionAnalysisLink question={question} key={`analysis-${question.id}`} />)}
      </span>
    </div>
  );
}

function SharedMultipleAnswerReview({ results }: { results: QuestionResult[] }) {
  const summary = results.find((result) => result.shared_response && result.shared_response_score !== undefined);
  if (!summary || summary.shared_response_score === summary.shared_response_total) return null;
  const correct = summary.selected_correct_answers || [];
  const incorrect = summary.selected_incorrect_answers || [];
  const missed = summary.missed_correct_answers || [];
  return (
    <span className="inline-answer-review shared-multiple-answer-review">
      <span>本组答对 <b>{summary.shared_response_score}/{summary.shared_response_total}</b></span>
      {correct.length ? <strong>选对 <b>{correct.join("、")}</b></strong> : null}
      {incorrect.length ? <span>误选 <b>{incorrect.join("、")}</b></span> : null}
      {missed.length ? <span>漏选 <b>{missed.join("、")}</b></span> : null}
    </span>
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
  const [resultSourcePart, setResultSourcePart] = useState<number | null>(null);
  const [selectedReviewQuestion, setSelectedReviewQuestion] = useState<QuestionResult | null>(null);
  const [showAnswerSentences, setShowAnswerSentences] = useState(false);
  const [showPassageTranslations, setShowPassageTranslations] = useState(false);
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
  const [timerActive, setTimerActive] = useState(false);
  const [paneRatio, setPaneRatio] = useState(44);
  const [annotationCount, setAnnotationCount] = useState(0);
  const timedOutRef = useRef(false);
  const activePartRef = useRef(1);
  const activeQuestionIdRef = useRef("");
  const activeQuestionLockUntilRef = useRef(0);
  const draftSnapshotRef = useRef<DraftState | null>(null);
  const initialHistorySessionRef = useRef(false);
  const { shouldCountStudyTime } = useStudyActivity(screen === "exam");

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
  const flaggedQuestionRows = useMemo(
    () => questionRows.filter(({ question }) => Boolean(flagged[String(question.id)])),
    [flagged, questionRows]
  );
  const flaggedCount = flaggedQuestionRows.length;
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
      if (!shouldCountStudyTime()) {
        setTimerActive(false);
        return;
      }
      setTimerActive(true);
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
  }, [paused, screen, shouldCountStudyTime]);

  useEffect(() => {
    if (screen !== "exam" || paused) setTimerActive(false);
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
        partElapsedSeconds: Object.fromEntries(
          selectedParts(test, partNumbers).map((part) => {
            const key = String(part.number);
            return [key, Math.max(0, Math.floor(partElapsedSeconds[key] || 0))];
          })
        ),
        questionElapsedSeconds: submittedQuestionTimings(test, partNumbers, questionElapsedSeconds),
        exam_mode: mode,
        part_numbers: partNumbers,
        timed_out: timedOut,
        annotations: readAnnotationsForSubmission(test.id, partNumbers)
      });
      setResult(response.result);
      setResultAnnotationsOpen(false);
      setResultSessionId(response.session_id);
      setHistoryEntrySource(false);
      setSelectedReviewQuestion(null);
      setShowAnswerSentences(false);
      setShowPassageTranslations(false);
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
      if (draft) {
        const restoredFlaggedCount = Object.values(draft.flagged || {}).filter(Boolean).length;
        setNotice(restoredFlaggedCount
          ? `已恢复答案、计时和 ${restoredFlaggedCount} 道标记题。可点击底部“检查标记”逐题复查。`
          : "已从草稿管理器继续上次未完成的答案和计时。");
      }
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
    const removing = ids.some((questionId) => flagged[questionId]);
    setFlagged((current) => {
      const next = { ...current };
      for (const questionId of ids) next[questionId] = !removing;
      return next;
    });
    const numbers = questionRows
      .filter(({ question }) => ids.includes(String(question.id)))
      .map(({ question }) => questionNumber(question));
    const label = numbers.length ? `第 ${numbers.join("、")} 题` : "当前题";
    setNotice(removing
      ? `已取消${label}的检查标记。`
      : `已标记${label}。可点击底部“检查标记”返回复查。`);
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
      setSelectedReviewQuestion(null);
      setShowAnswerSentences(false);
      setShowPassageTranslations(false);
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
    const activeDockItem = dockQuestions.find((item) => item.controlId === activeQuestionId)
      || dockQuestions.find((item) => Number(item.part.number) === activePart);
    const sharedActiveQuestionIds = activeDockItem ? sharedQuestionIds(activeDockItem.group) : [];
    const activeFlagQuestionIds = activeDockItem
      ? (sharedActiveQuestionIds.length ? sharedActiveQuestionIds : [String(activeDockItem.question.id)])
      : [];
    const activeQuestionFlagged = activeFlagQuestionIds.some((questionId) => Boolean(flagged[questionId]));
    const seenFlagTargets = new Set<string>();
    const flaggedDockTargets = dockQuestions.filter((item) => {
      if (!flagged[String(item.question.id)]) return false;
      const key = `${item.part.number}:${item.controlId}`;
      if (seenFlagTargets.has(key)) return false;
      seenFlagTargets.add(key);
      return true;
    });
    const currentDockIndex = dockQuestions.findIndex((item) => item.controlId === activeQuestionId);
    const moveDock = (direction: -1 | 1) => {
      const fallbackIndex = dockQuestions.findIndex((item) => Number(item.part.number) === activePart);
      const baseIndex = currentDockIndex >= 0 ? currentDockIndex : fallbackIndex;
      const target = dockQuestions[Math.max(0, Math.min(dockQuestions.length - 1, baseIndex + direction))];
      if (target) scrollToQuestion(target.controlId, Number(target.part.number));
    };
    const reviewNextFlagged = () => {
      if (!flaggedDockTargets.length) return;
      const currentFlaggedIndex = flaggedDockTargets.findIndex((item) =>
        item.controlId === activeQuestionId && Number(item.part.number) === activePart
      );
      const target = flaggedDockTargets[(currentFlaggedIndex + 1) % flaggedDockTargets.length];
      scrollToQuestion(target.controlId, Number(target.part.number));
      setNotice(`正在检查第 ${questionNumber(target.question)} 题。修改确认后可取消标记。`);
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
        data-source-visual={Boolean(active?.source_html)}
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
            <small className={timerActive ? "study-timer-status active" : "study-timer-status idle"}>
              {timerActive ? "活跃计时" : "静止暂停"}
            </small>
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
              const markedMessage = flaggedCount ? `还有 ${flaggedCount} 道题标记为待检查。` : "";
              if (window.confirm(`确定交卷吗？当前已完成 ${answeredCount}/${questionRows.length} 题。${markedMessage}`)) {
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
              <PassageDisplay part={active} />
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
          <div className="dock-review-actions" aria-label="标记题复查">
            <button
              type="button"
              className={activeQuestionFlagged ? "dock-flag-button active" : "dock-flag-button"}
              disabled={!activeFlagQuestionIds.length}
              aria-pressed={activeQuestionFlagged}
              aria-label={activeQuestionFlagged ? "取消当前题标记" : "标记当前题"}
              onClick={() => toggleFlag(activeFlagQuestionIds)}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M6 21V4m1 1h10l-1.6 4L17 13H7" />
              </svg>
              <span>{activeQuestionFlagged ? "取消标记" : "标记本题"}</span>
            </button>
            <button
              type="button"
              className="dock-review-button"
              disabled={!flaggedDockTargets.length}
              onClick={reviewNextFlagged}
              aria-label={flaggedCount ? `检查标记题，共 ${flaggedCount} 题` : "没有标记题"}
            >
              <span>检查标记</span>
              <strong>{flaggedCount}</strong>
            </button>
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
              <ul><li>拖动中间分隔线可在 30%–70% 范围调整文章宽度。</li><li>底部“标记本题”可记录不确定的题；“检查标记”会跨 Part 逐题带你返回复查。</li><li>暂停会冻结计时，不会清空答案。</li><li>答案和标记不会自动保存；点击“保存草稿”后，才可从“管理草稿”继续。</li><li>普通退出或从题卡再次开始都会创建空白练习。</li></ul>
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
    const showDetailedReview = historyEntrySource;
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
    const highlightedReviewQuestions = showAnswerSentences
      ? activeReviewQuestions
      : selectedReviewQuestion && Number(selectedReviewQuestion.part_number) === Number(activeReviewPart?.number)
        ? [selectedReviewQuestion]
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
          {showDetailedReview ? <a href="#result-performance">分项表现</a> : null}
          {resultAnnotations.length ? (
            <a href="#result-annotations" onClick={() => setResultAnnotationsOpen(true)}>高亮与笔记</a>
          ) : null}
        </nav>
        <div className="result-hero" id="result-overview">
          <div>
            <p className="eyebrow">{showDetailedReview ? "DETAILED SCORE REPORT" : "SUBMISSION RESULT"}</p>
            <h1>{result.test_title}</h1>
            <p>{showDetailedReview ? "练习记录详细报告 · 完整分项表现与逐题解析。" : "交卷完成 · 详细分项表现与逐题复盘已保存到练习记录。"}</p>
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
            <p>{showDetailedReview
              ? (result.wrong_questions.length ? "下方可按需展开错题和未作答题解析。" : "可以在逐题复盘中展开查看全部题目的答案依据。")
              : "详细分项表现与逐题解析已保存，可随时前往练习记录查看。"}</p>
          </div>
          <a
            href={showDetailedReview ? "#result-source-review" : "/history"}
          >
            {showDetailedReview ? "回看题目解析" : "前往练习记录"}
          </a>
        </section>
        {result.ai_paraphrase_summary ? (
          <section className="result-ai-paraphrase-summary">
            <div>
              <span>AI 错题同义替换</span>
              <strong>
                {result.ai_paraphrase_summary.status === "completed"
                  ? `已自动记录 ${result.ai_paraphrase_summary.saved_count} 条`
                  : result.ai_paraphrase_summary.reason === "ai_not_configured"
                    ? "AI 未配置，暂未自动记录"
                    : "本次未生成可记录内容"}
              </strong>
              <p>只处理错题；题目表达必须来自题目/选项/说明，原文表达必须来自原文证据。</p>
            </div>
            <a href="/vocabulary">去词汇本查看</a>
          </section>
        ) : null}
        <section className="result-section result-source-review" id="result-source-review">
          <header className="result-section-heading">
            <div><span>SOURCE REVIEW</span><h2>原文与我的作答记录</h2></div>
            <p>按 Part 恢复考试时的原文，右侧逐题对照你提交的答案和正确答案；包含错题的 Part 默认展开。</p>
          </header>
          {activeReviewPart ? (
            <div className="result-source-workbench">
              <div className="result-source-view-tools">
                <span>点击题号解析，可自动定位原文答案句</span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={showAnswerSentences}
                  className={showAnswerSentences ? "active" : ""}
                  onClick={() => setShowAnswerSentences((visible) => !visible)}
                >
                  答案句<i aria-hidden="true" />
                </button>
                <button
                  type="button"
                  role="switch"
                  aria-checked={showPassageTranslations}
                  className={showPassageTranslations ? "active" : ""}
                  onClick={() => setShowPassageTranslations((visible) => !visible)}
                >
                  翻译<i aria-hidden="true" />
                </button>
              </div>
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
                          onClick={() => {
                            setResultSourcePart(Number(part.number));
                            setSelectedReviewQuestion(null);
                          }}
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
                                  onClick={() => {
                                    setSelectedReviewQuestion(question);
                                    document.getElementById(`question-${question.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                                  }}
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
                  <div className="result-source-scroll">
                    <ResultPassageDisplay
                      key={`${activeReviewPart.number}:${highlightedReviewQuestions.map((question) => question.id).join(",")}:translation-${showPassageTranslations}`}
                      part={activeReviewPart}
                      questions={highlightedReviewQuestions}
                      showTranslations={showPassageTranslations}
                    />
                  </div>
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
                              onOpenAnalysis={setSelectedReviewQuestion}
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
        {showDetailedReview ? <>
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
        </> : null}
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
        {selectedReviewQuestion ? (
          <ResultQuestionAnalysisDialog
            question={selectedReviewQuestion}
            sessionId={resultSessionId}
            onClose={() => setSelectedReviewQuestion(null)}
          />
        ) : null}
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
              <article key={draft.key}><div><strong>{draft.testTitle || draft.testId}</strong><span>{draft.mode || "练习"} · Part {(draft.partNumbers || []).join(",") || "1–3"} · 已答 {Object.values(draft.answers || {}).filter(answerIsPresent).length} 题 · 标记 {Object.values(draft.flagged || {}).filter(Boolean).length} 题 · 标注 {draft.annotations?.length || 0} 条</span><small>{draft.updatedAt ? formatDate(draft.updatedAt) : "旧草稿"}</small></div>
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
  // Gap-fill placeholders stored as $questionId$ (4+ digits) must render as blanks.
  return value
    .replace(/\$\d{4,}\$/g, "_____")
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

function selectionIsInside(container: HTMLElement): boolean {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return false;
  const common = selection.getRangeAt(0).commonAncestorContainer;
  const commonElement = common.nodeType === Node.ELEMENT_NODE
    ? common as Element
    : common.parentElement;
  return Boolean(commonElement && container.contains(commonElement));
}

function preventAnswerToggleForSelection(event: ReactMouseEvent<HTMLElement>) {
  if (!selectionIsInside(event.currentTarget)) return;
  event.preventDefault();
  event.stopPropagation();
}

function prepareMatchingTextSelection(event: ReactPointerEvent<HTMLDivElement>) {
  if (!(event.target as Element).closest(".question-annotation-unit")) return;
  const card = event.currentTarget;
  card.draggable = false;
  const restore = () => {
    card.draggable = true;
    window.removeEventListener("pointerup", restore);
    window.removeEventListener("pointercancel", restore);
  };
  window.addEventListener("pointerup", restore, { once: true });
  window.addEventListener("pointercancel", restore, { once: true });
}

function sourceQuestionsForGroup(group: PublicQuestionGroup, source: SourceQuestionGroup): PublicQuestion[] {
  const start = Number(source.display_start || 0);
  const end = Number(source.display_end || start);
  const indexStart = Number(source.start_index || 0);
  const indexEnd = Number(source.end_index || indexStart);
  const displayMatched = group.questions.filter((question) => {
    const number = Number(question.display_number ?? question.number);
    return Number.isFinite(number) && start > 0 && number >= start && number <= end;
  });
  const indexMatched = group.questions.filter((question) => {
    const number = Number(question.display_number ?? question.number);
    return Number.isFinite(number) && indexStart > 0 && number >= indexStart && number <= indexEnd;
  });
  const singleSourceGroup = (group.source_question_groups?.length || 0) <= 1;
  if (singleSourceGroup && indexMatched.length > displayMatched.length) return indexMatched;
  return displayMatched.length ? displayMatched : group.questions;
}

function escapeSourceAttribute(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function sourceQuestionsHtmlWithControls(
  source: SourceQuestionGroup,
  questions: PublicQuestion[]
): string {
  let slot = 0;
  const control = () => {
    const question = questions[Math.min(slot, Math.max(0, questions.length - 1))];
    slot += 1;
    if (!question) return "";
    const id = String(question.id);
    return `<input id="question-${escapeSourceAttribute(id)}" data-source-answer-id="${escapeSourceAttribute(id)}" autocomplete="off" spellcheck="false" aria-label="第${questionNumber(question)}题答案">`;
  };
  let rendered = String(source.questions_html || "").replace(/(?:\.{4,}|_{4,})/g, control);
  if (slot === 0 && questions.length) {
    rendered += `<div class="source-fallback-controls">${questions.map(() => control()).join("")}</div>`;
  }
  return rendered;
}

function SourceHtmlQuestionBlock({
  group,
  source,
  answers,
  flagged,
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  source: SourceQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const onOpenAnalysis = useContext(ReviewAnalysisContext);
  const questions = useMemo(() => sourceQuestionsForGroup(group, source), [group, source]);
  const rendered = useMemo(
    () => sourceQuestionsHtmlWithControls(source, questions),
    [questions, source]
  );
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return undefined;
    const handleSourceControl = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) return;
      const id = target.dataset.sourceAnswerId;
      if (id) onAnswer(id, target.value);
    };
    content.addEventListener("input", handleSourceControl);
    content.addEventListener("change", handleSourceControl);
    return () => {
      content.removeEventListener("input", handleSourceControl);
      content.removeEventListener("change", handleSourceControl);
    };
  }, [onAnswer]);
  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    content.querySelectorAll(".question-analysis-link--source").forEach((element) => element.remove());
    for (const control of content.querySelectorAll<HTMLInputElement>("input[data-source-answer-id]")) {
      const id = control.dataset.sourceAnswerId;
      const value = id ? answers[id] : "";
      const nextValue = typeof value === "string" ? value : "";
      if (control.value !== nextValue) control.value = nextValue;
      if (id && flagged[id]) control.dataset.flagged = "true";
      else delete control.dataset.flagged;
      const reviewResult = id ? reviewResults?.get(id) : undefined;
      if (reviewResult) {
        const reviewStatus = questionReviewStatus(reviewResult);
        control.dataset.reviewStatus = reviewStatus;
        control.placeholder = reviewStatus === "unanswered" ? "未作答" : "";
        if (onOpenAnalysis) {
          const link = document.createElement("a");
          link.className = "question-analysis-link question-analysis-link--source";
          link.href = `#question-${reviewResult.id}`;
          link.setAttribute("role", "button");
          link.setAttribute("aria-label", `查看第${reviewResult.number}题解释`);
          link.textContent = "解释";
          link.addEventListener("click", (event) => {
            event.preventDefault();
            onOpenAnalysis(reviewResult);
          });
          control.insertAdjacentElement("afterend", link);
        }
      } else {
        delete control.dataset.reviewStatus;
        control.placeholder = "";
      }
    }
    return () => content.querySelectorAll(".question-analysis-link--source").forEach((element) => element.remove());
  }, [answers, flagged, onOpenAnalysis, rendered, reviewResults]);
  const sourceContent = (
    <StableHtmlDiv
      className="source-questions-content question-annotation-unit"
      contentRef={contentRef}
      html={rendered}
    />
  );
  const reviewQuestions = questions
    .map((question) => reviewResults?.get(String(question.id)))
    .filter((question): question is QuestionResult => Boolean(question));
  return (
    <>
      {sourceContent}
      {questions.length ? (
        <div className="source-flag-controls" aria-label="标记题目">
          {questions.map((question) => {
            const id = String(question.id);
            const marked = Boolean(flagged[id]);
            return (
              <button
                type="button"
                className={marked ? "flag-button active" : "flag-button"}
                aria-pressed={marked}
                key={`source-flag-${id}`}
                onClick={() => onFlag(id)}
              >
                <span>Q{questionNumber(question)}</span>
                {marked ? "取消标记" : "标记此题"}
              </button>
            );
          })}
        </div>
      ) : null}
      {reviewQuestions.length ? (
        <div className="source-html-answer-review-summary" aria-label="填空题答案对照">
          <div className="correct-answers">
            <b>正确答案：</b>
            {reviewQuestions.map((question) => (
              <span className="source-answer-summary-item" key={`source-correct-${question.id}`}>
                <span>Q{question.number}</span>
                <strong>{reviewValueText(question.correct_answer) || "题库暂未提供"}</strong>
              </span>
            ))}
          </div>
          <div className="submitted-answers">
            <b>我的答案：</b>
            {reviewQuestions.map((question) => {
              const status = questionReviewStatus(question);
              return (
                <span className={`source-answer-summary-item ${status}`} key={`source-submitted-${question.id}`}>
                  <span>Q{question.number}</span>
                  <strong>{reviewValueText(question.user_answer) || "未作答"}</strong>
                </span>
              );
            })}
          </div>
        </div>
      ) : null}
    </>
  );
}

function sourceOptionDescription(option: { index?: string; content_html?: string }): string {
  const code = String(option?.index || "").trim();
  const text = String(option?.content_html || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || text.localeCompare(code, undefined, { sensitivity: "accent" }) === 0) return "";
  if (text.localeCompare(`Section ${code}`, undefined, { sensitivity: "accent" }) === 0) return "";
  if (text.localeCompare(`Paragraph ${code}`, undefined, { sensitivity: "accent" }) === 0) return "";
  return text;
}

type SourceMatchingExampleRow = {
  label: string;
  answer: string;
};

function sourceHtmlTextLines(html: string): string[] {
  return String(html || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|li|tr|h[1-6])>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;|&#x0*a0;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .split(/\r?\n/)
    .map((line) => repairDisplayText(line).replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

function sourceMatchingExampleRows(source: SourceQuestionGroup): SourceMatchingExampleRow[] {
  const optionCodes = (source.match_options || [])
    .map((option) => String(option.index || "").trim())
    .filter(Boolean);
  if (!optionCodes.length) return [];

  const optionCode = new Map(optionCodes.map((code) => [code.toLocaleLowerCase(), code]));
  const parseRow = (line: string): SourceMatchingExampleRow | null => {
    const match = line.match(/^(.*?)\s+(\S+)\s*$/);
    if (!match) return null;
    const label = match[1].trim();
    const rawAnswer = match[2].replace(/[.,;:]$/, "");
    if (!label || !optionCode.has(rawAnswer.toLocaleLowerCase())) return null;
    return { label, answer: rawAnswer };
  };

  const lines = sourceHtmlTextLines(source.questions_html || "");
  const rows: SourceMatchingExampleRow[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!/^Example\s*:?\b/i.test(line)) continue;

    const inline = line.match(/^Example\s*:?\s*(.*?)\s+Answer\s*:?\s*(\S+)\s*$/i);
    if (inline) {
      const row = parseRow(`${inline[1]} ${inline[2]}`);
      if (row) rows.push(row);
      continue;
    }

    if (/^Example\s*:?\s*Answer\s*:?$/i.test(line)) {
      const row = parseRow(lines[index + 1] || "");
      if (row) rows.push(row);
    }
  }
  return rows.filter((row, index) => (
    rows.findIndex((candidate) => candidate.label === row.label && candidate.answer === row.answer) === index
  ));
}

function SourceMatchingMatrix({
  group,
  source,
  answers,
  flagged,
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  source: SourceQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const questions = sourceQuestionsForGroup(group, source);
  const options = source.match_options || [];
  const showOptionBank = options.some((option) => Boolean(sourceOptionDescription(option)));
  const exampleRows = sourceMatchingExampleRows(source);
  return (
    <>
      {exampleRows.length ? (
        <div className="source-matching-example" role="group" aria-label="示例答案">
          <div className="source-matching-example-header">
            <span>Example:</span>
            <span>Answer</span>
          </div>
          {exampleRows.map((row) => (
            <div className="source-matching-example-row" key={`${row.label}-${row.answer}`}>
              <span className="question-annotation-unit">{row.label}</span>
              <strong className="question-annotation-unit">{row.answer}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {showOptionBank ? (
        <aside className="source-option-bank">
          {source.options_title ? <strong>{source.options_title}</strong> : null}
          {options.map((option) => (
            <div key={`${source.position}-${option.index}`}>
              <b>{option.index}</b>
              <StableHtmlSpan className="question-annotation-unit" html={option.content_html || ""} />
            </div>
          ))}
        </aside>
      ) : null}
      <div className="source-matching-matrix-wrap" role="region" aria-label="匹配题答题表" tabIndex={0}>
        <table className="source-matching-matrix">
          <thead>
            <tr>
              <th scope="col"><span className="sr-only">题目</span></th>
              {options.map((option) => <th scope="col" key={option.index}>{option.index}</th>)}
            </tr>
          </thead>
          <tbody>
            {questions.map((question) => {
              const id = String(question.id);
              const value = answers[id];
              const marked = Boolean(flagged[id]);
              return (
                <tr id={`question-${id}`} key={id} className={`${answerIsPresent(value) ? "answered" : ""}${marked ? " flagged" : ""}`}>
                  <th scope="row">
                    <div className="source-matrix-question-heading">
                      <span>
                        <span className="source-matrix-question-number">{questionNumber(question)}</span>
                        <span className="question-annotation-unit">{displayMarkup(question.prompt)}</span>
                      </span>
                      <button
                        type="button"
                        className={marked ? "flag-button active" : "flag-button"}
                        aria-pressed={marked}
                        onClick={() => onFlag(id)}
                      >
                        {marked ? "取消标记" : "标记此题"}
                      </button>
                    </div>
                    <InlineQuestionReview question={reviewResults?.get(id)} />
                  </th>
                  {options.map((option) => {
                    const code = String(option.index || "");
                    return (
                      <td key={code}>
                        <label className="source-matrix-radio">
                          <input
                            type="radio"
                            name={`source-answer-${id}`}
                            checked={value === code}
                            onChange={() => onAnswer(id, code)}
                          />
                          <span aria-hidden="true" />
                          <span className="sr-only">第{questionNumber(question)}题选择 {code}</span>
                        </label>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SourceStructuredQuestionBlock({
  group,
  source,
  answers,
  flagged,
  reviewResults,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  source: SourceQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  const questions = sourceQuestionsForGroup(group, source);
  const sourceQuestions = source.structured_questions || [];
  const questionType = Number(source.question_type);
  return (
    <>
      {sourceQuestions.map((sourceQuestion, index) => {
        const question = questions[Math.min(index, Math.max(0, questions.length - 1))];
        if (!question) return null;
        const id = String(question.id);
        const inferredSharedResponse = questionType === 2
          && sourceQuestions.length === 1
          && questions.length > 1;
        const answerIds = inferredSharedResponse || (questionType === 2 && group.shared_response)
          ? questions.map((item) => String(item.id))
          : [id];
        const sourceReviewResults = answerIds
          .map((answerId) => reviewResults?.get(answerId))
          .filter((result): result is QuestionResult => Boolean(result));
        const value = answerIds.map((answerId) => answers[answerId]).find(Array.isArray)
          || answers[answerIds[0]];
        const selected = Array.isArray(value) ? value : [];
        const displayNumber = questionType === 2 && answerIds.length > 1
          ? `${questionNumber(questions[0])}–${questionNumber(questions[questions.length - 1])}`
          : String(questionNumber(question));
        const marked = answerIds.some((answerId) => Boolean(flagged[answerId]));
        const answered = answerIsPresent(value);
        return (
          <article className={`source-question-row${marked ? " flagged" : ""}${answered ? " answered" : ""}`} id={`question-${id}`} key={`${source.position}-${id}-${index}`}>
            <div className="source-question-prompt">
              <strong>{displayNumber}</strong>
              <StableHtmlSpan className="question-annotation-unit" html={sourceQuestion.content_html || ""} />
              <div className="source-question-tools">
                <button
                  type="button"
                  className={marked ? "flag-button active" : "flag-button"}
                  aria-pressed={marked}
                  onClick={() => onFlag(answerIds)}
                >
                  {marked ? "取消标记" : "标记此题"}
                </button>
              </div>
            </div>
            <div className="source-answer-options">
              {(sourceQuestion.options || []).map((option, optionIndex) => {
                const optionText = String(option.content_html || "").replace(/<[^>]+>/g, "").trim();
                const code = questionType === 1 || questionType === 2
                  ? String.fromCharCode(65 + optionIndex)
                  : optionText;
                const checked = questionType === 2 ? selected.includes(code) : value === code;
                return (
                  <label
                    className={answerReviewClass(code, sourceReviewResults).trim()}
                    key={`${id}-${code}-${optionIndex}`}
                    onClickCapture={preventAnswerToggleForSelection}
                  >
                    <input
                      type={questionType === 2 ? "checkbox" : "radio"}
                      name={`source-answer-${id}`}
                      checked={checked}
                      onChange={(event) => {
                        if (questionType !== 2) {
                          onAnswer(answerIds, code);
                          return;
                        }
                        const requiredChoices = Number(source.required_choices || group.required_choices || 0);
                        if (event.target.checked && requiredChoices > 0 && selected.length >= requiredChoices) {
                          return;
                        }
                        const next = event.target.checked
                          ? [...selected.filter((item) => item !== code), code]
                          : selected.filter((item) => item !== code);
                        onAnswer(answerIds, next);
                      }}
                    />
                    {questionType === 1 || questionType === 2 ? <b>{code}</b> : null}
                    <StableHtmlSpan className="question-annotation-unit" html={option.content_html || ""} />
                  </label>
                );
              })}
            </div>
            {answerIds.length > 1
              ? <QuestionReviewActions results={sourceReviewResults} />
              : <InlineQuestionReview question={reviewResults?.get(id)} />}
          </article>
        );
      })}
    </>
  );
}

function SourceQuestionGroupControl({
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
  return (
    <section className="question-group question-group--source">
      {(group.source_question_groups || []).map((source) => (
        <section
          className="source-question-block"
          data-source-question-type={source.question_type}
          data-source-interaction-mode={source.interaction_mode || ""}
          key={`${source.position}-${source.navigation || "source"}`}
        >
          {source.instructions_html ? (
            <StableHtmlDiv
              className="question-instructions question-annotation-unit question-instructions--source"
              html={source.instructions_html}
            />
          ) : null}
          {source.interaction_mode === "matching_matrix" ? (
            <SourceMatchingMatrix
              group={group}
              source={source}
              answers={answers}
              flagged={flagged}
              reviewResults={reviewResults}
              onAnswer={onAnswer}
              onFlag={onFlag}
            />
          ) : source.questions_html ? (
            <SourceHtmlQuestionBlock
              group={group}
              source={source}
              answers={answers}
              flagged={flagged}
              reviewResults={reviewResults}
              onAnswer={onAnswer}
              onFlag={onFlag}
            />
          ) : (
            <SourceStructuredQuestionBlock
              group={group}
              source={source}
              answers={answers}
              flagged={flagged}
              reviewResults={reviewResults}
              onAnswer={onAnswer}
              onFlag={onFlag}
            />
          )}
        </section>
      ))}
    </section>
  );
}

function QuestionGroupControl({
  group,
  answers,
  flagged,
  reviewResults,
  onOpenAnalysis,
  onAnswer,
  onFlag
}: {
  group: PublicQuestionGroup;
  answers: Record<string, AnswerValue>;
  flagged: Record<string, boolean>;
  reviewResults?: Map<string, QuestionResult>;
  onOpenAnalysis?: (question: QuestionResult) => void;
  onAnswer: (questionIds: string | string[], value: AnswerValue) => void;
  onFlag: (questionIds: string | string[]) => void;
}) {
  if (group.source_question_groups?.length) {
    return (
      <ReviewAnalysisContext.Provider value={onOpenAnalysis || null}>
        <SourceQuestionGroupControl
          group={group}
          answers={answers}
          flagged={flagged}
          reviewResults={reviewResults}
          onAnswer={onAnswer}
          onFlag={onFlag}
        />
      </ReviewAnalysisContext.Provider>
    );
  }
  const subtype = group.question_subtype || group.question_type;
  const matching = subtype.startsWith("matching_");
  const firstQuestion = group.questions[0];
  const groupOptions = firstQuestion ? optionsFor(group, firstQuestion) : [];
  const matchingHasDescriptions = matching && groupOptions.some((option) => Boolean(optionDisplayText(option)));
  const useMatchingMatrix = matching && groupOptions.length > 0 && !matchingHasDescriptions && !group.shared_response;
  const structuredCompletion = ["table_completion", "flow_chart_completion", "summary_completion", "note_completion", "sentence_completion", "diagram_label_completion", "short_answer"]
    .includes(subtype) && Boolean(group.content_template || group.table?.rows?.length || group.table?.content?.length);

  return (
    <ReviewAnalysisContext.Provider value={onOpenAnalysis || null}>
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
                      <InlineQuestionReview question={reviewResult} />
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
    </ReviewAnalysisContext.Provider>
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
                onPointerDown={prepareMatchingTextSelection}
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
              <InlineQuestionReview question={reviewResult} />
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
            <InlineQuestionReview question={reviewResults?.get(id)} />
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
            <label key={option} className={`${value === option ? "selected" : ""}${answerReviewClass(option, reviewResults)}`} onClickCapture={preventAnswerToggleForSelection}>
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
                <label key={option.code} className={`${selected ? "selected" : ""}${answerReviewClass(option.code, reviewResults)}`} onClickCapture={preventAnswerToggleForSelection}>
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
            <label key={option.code} className={`${value === option.code ? "selected" : ""}${answerReviewClass(option.code, reviewResults)}`} onClickCapture={preventAnswerToggleForSelection}>
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
      <QuestionReviewActions results={reviewResults} />
    </article>
  );
}
