"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  clientSubmissionId: string;
};

const USER_ID = "owner";

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

function optionsFor(group: PublicQuestionGroup, question: PublicQuestion): QuestionOption[] {
  if (group.normalized_options?.length) return group.normalized_options;
  const raw = question.options?.length
    ? question.options
    : Array.isArray(group.shared_options) && group.shared_options.length
      ? group.shared_options
      : group.options || [];
  return raw.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item));
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
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [flagged, setFlagged] = useState<Record<string, boolean>>({});
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const [clientSubmissionId, setClientSubmissionId] = useState("");
  const [draftKey, setDraftKey] = useState("");
  const [result, setResult] = useState<ScoringResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const timedOutRef = useRef(false);

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
    () => questionRows.filter(({ question }) => {
      const value = answers[String(question.id)];
      return Array.isArray(value) ? value.length > 0 : Boolean(String(value || "").trim());
    }).length,
    [questionRows, answers]
  );

  useEffect(() => {
    if (screen !== "exam") return;
    const timer = window.setInterval(() => {
      setElapsedSeconds((value) => value + 1);
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
  }, [screen]);

  useEffect(() => {
    if (screen !== "exam" || !draftKey || !clientSubmissionId) return;
    const draft: DraftState = {
      answers,
      flagged,
      elapsedSeconds,
      remainingSeconds,
      clientSubmissionId
    };
    window.localStorage.setItem(draftKey, JSON.stringify(draft));
  }, [answers, clientSubmissionId, draftKey, elapsedSeconds, flagged, remainingSeconds, screen]);

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
  }, [answers, clientSubmissionId, draftKey, elapsedSeconds, mode, partNumbers, refreshHistory, submitting, test]);

  useEffect(() => {
    if (screen === "exam" && timedOutRef.current && remainingSeconds === 0 && !submitting) {
      void submitCurrent(true);
    }
  }, [remainingSeconds, screen, submitCurrent, submitting]);

  async function startExam(testId: string, nextMode: ExamMode, nextParts: number[]) {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      const loaded = await fetchPublicTest(testId);
      const resolvedParts = nextParts.length ? nextParts : loaded.parts.map((part) => Number(part.number));
      const key = `ielts-platform-draft:${testId}:${nextMode}:${resolvedParts.join("-")}`;
      let draft: DraftState | null = null;
      try {
        const raw = window.localStorage.getItem(key);
        draft = raw ? JSON.parse(raw) as DraftState : null;
      } catch {
        draft = null;
      }
      const limit = nextMode === "mock_exam" ? 3600 : nextMode === "part_practice" ? 1200 : null;
      setTest(loaded);
      setMode(nextMode);
      setPartNumbers(nextParts);
      setActivePart(resolvedParts[0] || 1);
      setAnswers(draft?.answers || {});
      setFlagged(draft?.flagged || {});
      setElapsedSeconds(draft?.elapsedSeconds || 0);
      setRemainingSeconds(draft?.remainingSeconds ?? limit);
      setClientSubmissionId(draft?.clientSubmissionId || newSubmissionId());
      setDraftKey(key);
      setResult(null);
      timedOutRef.current = false;
      if (draft) setNotice("已恢复上次未交卷的答案和计时。");
      setScreen("exam");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "试卷加载失败");
    } finally {
      setLoading(false);
    }
  }

  function updateAnswer(questionId: string, value: AnswerValue) {
    setAnswers((current) => ({ ...current, [questionId]: value }));
  }

  function toggleFlag(questionId: string) {
    setFlagged((current) => ({ ...current, [questionId]: !current[questionId] }));
  }

  function scrollToQuestion(questionId: string, partNumber: number) {
    setActivePart(partNumber);
    window.setTimeout(() => {
      document.getElementById(`question-${questionId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 20);
  }

  function leaveExam() {
    if (answeredCount && !window.confirm("答案已自动保存在本机草稿。确定返回题库吗？")) return;
    setScreen("library");
    setNotice("");
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
    for (const item of tests) {
      const rows = groups.get(item.book_number) || [];
      rows.push(item);
      groups.set(item.book_number, rows);
    }
    return [...groups.entries()].sort((a, b) => b[0] - a[0]);
  }, [tests]);

  if (screen === "exam" && test) {
    const active = currentParts.find((part) => Number(part.number) === activePart) || currentParts[0];
    return (
      <div className="exam-workbench" role="application" aria-label="IELTS阅读考试工作台">
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
          <button type="button" className="exam-ghost-button" onClick={leaveExam}>返回题库</button>
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
        <div className="exam-part-tabs" role="tablist" aria-label="选择Part">
          {currentParts.map((part) => (
            <button
              type="button"
              key={part.number}
              className={Number(part.number) === activePart ? "active" : ""}
              onClick={() => setActivePart(Number(part.number))}
            >Part {part.number}</button>
          ))}
        </div>
        {active ? (
          <div className="exam-grid">
            <section className="passage-pane" aria-label={`Part ${active.number} 原文`}>
              <div className="pane-heading">
                <span>READING PASSAGE</span>
                <h1>{active.article_title || active.title}</h1>
                {active.subtitle ? <p>{active.subtitle}</p> : null}
              </div>
              <div className="passage-copy">
                {(active.paragraphs || []).map((paragraph, index) => (
                  <div className="passage-paragraph" key={`${paragraph.index ?? index}-${paragraph.text.slice(0, 20)}`}>
                    {paragraph.label ? <strong>{paragraph.label}</strong> : null}
                    <p>{paragraph.text}</p>
                  </div>
                ))}
              </div>
            </section>
            <section className="questions-pane" aria-label={`Part ${active.number} 题目`}>
              {active.groups.map((group, groupIndex) => (
                <section className="question-group" key={group.id || `${active.number}-${groupIndex}`}>
                  <div className="question-instructions">
                    <span>{group.question_label || group.question_subtype}</span>
                    <p>{group.instructions}</p>
                  </div>
                  {group.questions.map((question) => (
                    <QuestionControl
                      key={question.id}
                      group={group}
                      question={question}
                      value={answers[String(question.id)]}
                      flagged={Boolean(flagged[String(question.id)])}
                      onChange={(value) => updateAnswer(String(question.id), value)}
                      onFlag={() => toggleFlag(String(question.id))}
                    />
                  ))}
                </section>
              ))}
            </section>
            <aside className="question-rail" aria-label="题号导航">
              {currentParts.map((part) => (
                <div key={part.number}>
                  <strong>Part {part.number}</strong>
                  <div className="question-number-grid">
                    {part.groups.flatMap((group) => group.questions).map((question) => {
                      const id = String(question.id);
                      const value = answers[id];
                      const answered = Array.isArray(value) ? value.length > 0 : Boolean(String(value || "").trim());
                      const className = [answered ? "answered" : "", flagged[id] ? "flagged" : ""].filter(Boolean).join(" ");
                      return (
                        <button
                          type="button"
                          key={id}
                          className={className}
                          onClick={() => scrollToQuestion(id, Number(part.number))}
                          aria-label={`第${questionNumber(question)}题${answered ? "，已作答" : ""}${flagged[id] ? "，已标记" : ""}`}
                        >{questionNumber(question)}</button>
                      );
                    })}
                  </div>
                </div>
              ))}
              <div className="rail-legend"><span className="answered" />已答 <span className="flagged" />标记</div>
            </aside>
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
              <article key={part.part_number}><span>Part {part.part_number}</span><strong>{part.score}/{part.total}</strong><small>{part.accuracy}%</small></article>
            ))}
          </div>
        </section>
        <section className="result-section">
          <h2>错题复盘</h2>
          {result.wrong_questions.length ? (
            <div className="wrong-result-list">
              {result.wrong_questions.map((question) => (
                <article className="wrong-result-card" key={question.id}>
                  <div><span>Q{question.number} · {question.question_type}</span><strong>{question.prompt}</strong></div>
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
        <p>46套真实G类阅读题库。模考过程不显示答案、解析或AI提示；交卷后由服务端确定性判分。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="practice-stat-strip">
        <article><span>完整套题</span><strong>{tests.length || 46}</strong></article>
        <article><span>总题量</span><strong>1,840</strong></article>
        <article><span>真实判分对照</span><strong>138/138</strong></article>
        <article><span>完整模考</span><strong>60分钟</strong></article>
      </section>
      <div className="library-layout">
        <section className="book-library" aria-label="题库列表">
          {loading ? <div className="library-loading">正在加载题库…</div> : groupedTests.map(([bookNumber, items]) => (
            <section className="book-section" key={bookNumber}>
              <div className="book-section-heading"><div><span>CAMBRIDGE IELTS</span><h2>剑雅 {bookNumber}</h2></div><small>{items.length} 套 · 每套40题</small></div>
              <div className="test-card-grid">
                {items.map((item) => (
                  <article className="test-card" key={item.id}>
                    <div><span>{item.name}</span><strong>{item.title}</strong><small>3 Parts · 40 Questions</small></div>
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
  const multi = subtype === "multiple_choice_multiple" || Number(group.required_choices || 1) > 1;
  const matching = subtype.startsWith("matching_");

  return (
    <article className={flagged ? "question-card flagged" : "question-card"} id={`question-${id}`}>
      <div className="question-title-row">
        <span className="question-number">{number}</span>
        <p>{question.prompt}</p>
        <button type="button" className={flagged ? "flag-button active" : "flag-button"} onClick={onFlag}>{flagged ? "已标记" : "标记"}</button>
      </div>
      {judgement ? (
        <div className="answer-options judgement-options">
          {judgement.map((option) => (
            <label key={option} className={value === option ? "selected" : ""}>
              <input type="radio" name={`answer-${id}`} value={option} checked={value === option} onChange={() => onChange(option)} />
              <span>{option}</span>
            </label>
          ))}
        </div>
      ) : multi && options.length ? (
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
                    else if (current.length < Number(group.required_choices || 2)) onChange([...current, option.code]);
                  }}
                />
                <b>{option.code}</b><span>{option.text}</span>
              </label>
            );
          })}
        </div>
      ) : options.length && !matching && subtype === "multiple_choice_single" ? (
        <div className="answer-options choice-options">
          {options.map((option) => (
            <label key={option.code} className={value === option.code ? "selected" : ""}>
              <input type="radio" name={`answer-${id}`} checked={value === option.code} onChange={() => onChange(option.code)} />
              <b>{option.code}</b><span>{option.text}</span>
            </label>
          ))}
        </div>
      ) : options.length ? (
        <label className="select-answer">
          <span>选择答案</span>
          <select value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}>
            <option value="">请选择</option>
            {options.map((option) => <option key={option.code} value={option.code}>{option.code} · {option.text}</option>)}
          </select>
        </label>
      ) : (
        <label className="text-answer">
          <span>答案</span>
          <input
            value={typeof value === "string" ? value : ""}
            onChange={(event) => onChange(event.target.value)}
            autoComplete="off"
            spellCheck={false}
            aria-label={`第${number}题答案`}
          />
        </label>
      )}
      {value ? <button type="button" className="clear-answer" onClick={() => onChange(multi ? [] : "")}>清除答案</button> : null}
    </article>
  );
}
