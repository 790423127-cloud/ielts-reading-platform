"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  fetchTrainingCatalog,
  generateAbilitySet,
  submitAbilitySet,
  type AbilityQuestionItem,
  type AbilitySet,
  type AbilitySkill,
  type PublicQuestion,
  type PublicQuestionGroup,
  type QuestionOption,
  type ScoringResult
} from "@/lib/api";
import { useStudyActivity } from "@/lib/useStudyActivity";

type AnswerValue = string | string[];

function newSubmissionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `ability-${crypto.randomUUID()}`;
  }
  return `ability-${Date.now()}-${Math.random().toString(16).slice(2)}`;
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
  if (question.options?.length) {
    return question.options.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item));
  }
  if (group.normalized_options?.length) return group.normalized_options;
  const raw = Array.isArray(group.shared_options) && group.shared_options.length
    ? group.shared_options
    : group.options || [];
  return raw.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item));
}

function repairDisplayText(value: string): string {
  return value
    .replace(/\$\d{4,}\$/g, "_____")
    .replace(/^lt(?=\s)/, "It");
}

function formatSeconds(value: number): string {
  const minutes = Math.floor(Math.max(0, value) / 60);
  const seconds = Math.max(0, value) % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function AbilityTrainingCenter() {
  const [skills, setSkills] = useState<AbilitySkill[]>([]);
  const [questionTypes, setQuestionTypes] = useState<AbilitySkill[]>([]);
  const [catalogMode, setCatalogMode] = useState<"ability" | "question_type">("ability");
  const [activeSkillId, setActiveSkillId] = useState("");
  const [trainingSet, setTrainingSet] = useState<AbilitySet | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [result, setResult] = useState<ScoringResult | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [questionElapsedSeconds, setQuestionElapsedSeconds] = useState<Record<string, number>>({});
  const [activeQuestionId, setActiveQuestionId] = useState("");
  const [trainingMode, setTrainingMode] = useState<"free" | "timed">("free");
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
  const [timerActive, setTimerActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [clientSubmissionId, setClientSubmissionId] = useState("");
  const activeQuestionIdRef = useRef("");
  const { shouldCountStudyTime } = useStudyActivity(Boolean(trainingSet && !result));

  const loadSet = useCallback(async (
    skillId: string,
    cursor = 0,
    questionRefs: string[] = [],
    requestedMode: "free" | "timed" = "free"
  ) => {
    setGenerating(true);
    setError("");
    try {
      const generated = await generateAbilitySet(
        skillId,
        questionRefs.length || 8,
        cursor,
        questionRefs
      );
      setTrainingSet(generated);
      setAnswers({});
      setResult(null);
      setElapsedSeconds(0);
      setQuestionElapsedSeconds({});
      setActiveQuestionId(generated.items[0]?.ref_id || "");
      setTrainingMode(requestedMode);
      setRemainingSeconds(requestedMode === "timed" ? generated.items.length * 90 : null);
      setClientSubmissionId(newSubmissionId());
      setActiveSkillId(skillId);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "训练题生成失败");
    } finally {
      setGenerating(false);
    }
  }, []);

  const submit = useCallback(async () => {
    if (!trainingSet || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const response = await submitAbilitySet({
        user_id: "owner",
        client_submission_id: clientSubmissionId,
        skill_id: trainingSet.skill.id,
        question_refs: trainingSet.items.map((item) => item.ref_id),
        answers,
        elapsed_seconds: elapsedSeconds,
        question_elapsed_seconds: questionElapsedSeconds
      });
      setResult(response.result);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "能力训练提交失败");
    } finally {
      setSubmitting(false);
    }
  }, [answers, clientSubmissionId, elapsedSeconds, questionElapsedSeconds, submitting, trainingSet]);

  useEffect(() => {
    activeQuestionIdRef.current = activeQuestionId;
  }, [activeQuestionId]);

  useEffect(() => {
    const controller = new AbortController();
    fetchTrainingCatalog(controller.signal)
      .then((catalog) => {
        setSkills(catalog.skills);
        setQuestionTypes(catalog.questionTypes);
        const params = new URLSearchParams(window.location.search);
        const querySkill = params.get("skill") || "";
        const querySubtype = params.get("subtype") || "";
        const questionRef = params.get("question") || "";
        const questionRefs = (params.get("questions") || "").split(",").filter(Boolean).slice(0, 20);
        const requestedMode = params.get("mode") === "timed" ? "timed" : "free";
        const requestedId = querySubtype ? `subtype-${querySubtype}` : querySkill;
        const allTargets = [...catalog.skills, ...catalog.questionTypes];
        const selected = requestedId === "wrong-batch"
          ? { id: "wrong-batch", label: "错题混合再练", objective: "按已选范围重做权威原题", subtype_ids: [], source_policy: "verified_question_bank_only", available_questions: questionRefs.length }
          : allTargets.find((item) => item.id === requestedId) || catalog.skills[0];
        if (selected) {
          setActiveSkillId(selected.id);
          setTrainingMode(requestedMode);
          setCatalogMode(selected.id.startsWith("subtype-") ? "question_type" : "ability");
          if (questionRefs.length) void loadSet(selected.id, 0, questionRefs, requestedMode);
          else if (questionRef) void loadSet(selected.id, 0, [questionRef], requestedMode);
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "能力训练读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [loadSet]);

  useEffect(() => {
    if (!trainingSet || result) return;
    const timer = window.setInterval(() => {
      if (!shouldCountStudyTime()) {
        setTimerActive(false);
        return;
      }
      setTimerActive(true);
      setElapsedSeconds((value) => value + 1);
      const currentQuestionId = activeQuestionIdRef.current;
      if (currentQuestionId) {
        setQuestionElapsedSeconds((current) => ({
          ...current,
          [currentQuestionId]: (current[currentQuestionId] || 0) + 1
        }));
      }
      if (trainingMode === "timed") setRemainingSeconds((value) => value == null ? null : Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [trainingMode, trainingSet, result, shouldCountStudyTime]);

  useEffect(() => {
    if (!trainingSet || result) setTimerActive(false);
  }, [result, trainingSet]);

  useEffect(() => {
    if (!trainingSet || result) return;
    const elements = [...document.querySelectorAll<HTMLElement>("[data-ability-question-id]")];
    if (!elements.length) return;
    const visible = new Map<Element, IntersectionObserverEntry>();
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.set(entry.target, entry);
        else visible.delete(entry.target);
      }
      const closest = [...visible.values()].sort((left, right) =>
        Math.abs(left.boundingClientRect.top - window.innerHeight * 0.3)
        - Math.abs(right.boundingClientRect.top - window.innerHeight * 0.3)
      )[0];
      const id = (closest?.target as HTMLElement | undefined)?.dataset.abilityQuestionId;
      if (id) setActiveQuestionId(id);
    }, { rootMargin: "-15% 0px -55% 0px", threshold: [0, 0.25, 0.5] });
    for (const element of elements) observer.observe(element);
    return () => observer.disconnect();
  }, [result, trainingSet]);

  useEffect(() => {
    if (trainingSet && trainingMode === "timed" && remainingSeconds === 0 && !result && !submitting) {
      void submit();
    }
  }, [remainingSeconds, result, submit, submitting, trainingMode, trainingSet]);

  const visibleTargets = catalogMode === "ability" ? skills : questionTypes;
  const answeredCount = useMemo(() => {
    if (!trainingSet) return 0;
    return trainingSet.items.filter((item) => {
      const value = answers[item.ref_id];
      return Array.isArray(value) ? value.length > 0 : Boolean(String(value || "").trim());
    }).length;
  }, [answers, trainingSet]);

  function leaveUnsubmittedSet() {
    if (answeredCount > 0 && !window.confirm("当前答案尚未提交，返回后不会保存。确定放弃本组吗？")) return;
    setTrainingSet(null);
    setAnswers({});
    setElapsedSeconds(0);
    setQuestionElapsedSeconds({});
    setActiveQuestionId("");
    setClientSubmissionId("");
  }

  if (trainingSet) {
    return (
      <div className="page-wrap ability-session-page">
        <header className="ability-session-head">
          <div>
            <p className="eyebrow">VERIFIED QUESTION TRAINING</p>
            <h1>{trainingSet.skill.label}{trainingSet.training_kind === "question_type" ? "专项练习" : "能力训练"}</h1>
            <p>{trainingSet.skill.objective}</p>
          </div>
          <div className="ability-session-meta">
            <span>真实题库</span><strong>{trainingSet.items.length}题</strong>
            <span>{trainingMode === "timed" ? "剩余" : "用时"}</span><strong>{formatSeconds(trainingMode === "timed" ? remainingSeconds || 0 : elapsedSeconds)}</strong>
            <span>计时状态</span><strong className={timerActive ? "study-timer-state active" : "study-timer-state idle"}>{timerActive ? "活跃计时" : "静止暂停"}</strong>
            <span>本题 {activeQuestionId ? `Q${trainingSet.items.findIndex((item) => item.ref_id === activeQuestionId) + 1}` : ""}</span><strong>{formatSeconds(questionElapsedSeconds[activeQuestionId] || 0)}</strong>
          </div>
        </header>
        {error ? <div className="page-error">{error}</div> : null}

        {result ? (
          <section className="ability-result-panel">
            <div className="ability-result-score"><span>本组成绩</span><strong>{result.score}/{result.total}</strong><small>{result.accuracy}%</small></div>
            <div>
              <h2>{result.score === result.total ? "本组全部答对" : `需要复盘 ${result.wrong_questions.length} 题`}</h2>
              <p>专项训练不是完整40题，因此不会显示Band。结果已经保存到Session和错题库。</p>
            </div>
            <div className="ability-result-actions">
              <button type="button" className="secondary-button" onClick={() => setTrainingSet(null)}>返回训练列表</button>
              <button type="button" className="primary-button" onClick={() => void loadSet(trainingSet.skill.id, trainingSet.next_cursor, [], trainingMode)}>换一组真实题</button>
            </div>
          </section>
        ) : (
          <div className="ability-progress-bar"><span style={{ width: `${trainingSet.items.length ? answeredCount / trainingSet.items.length * 100 : 0}%` }} /><strong>{answeredCount}/{trainingSet.items.length} 已作答</strong></div>
        )}

        <div
          className="ability-question-list"
          onPointerDownCapture={(event) => {
            const element = (event.target as Element).closest<HTMLElement>("[data-ability-question-id]");
            if (element?.dataset.abilityQuestionId) setActiveQuestionId(element.dataset.abilityQuestionId);
          }}
          onFocusCapture={(event) => {
            const element = (event.target as Element).closest<HTMLElement>("[data-ability-question-id]");
            if (element?.dataset.abilityQuestionId) setActiveQuestionId(element.dataset.abilityQuestionId);
          }}
        >
          {trainingSet.items.map((item, index) => {
            const questionResult = result?.question_results.find((row) => row.id === item.ref_id);
            return (
              <AbilityQuestionCard
                key={item.ref_id}
                item={item}
                index={index}
                value={answers[item.ref_id]}
                disabled={Boolean(result)}
                result={questionResult}
                onChange={(value) => {
                  setActiveQuestionId(item.ref_id);
                  setAnswers((current) => ({ ...current, [item.ref_id]: value }));
                }}
              />
            );
          })}
        </div>
        {!result ? (
          <div className="ability-submit-bar">
            <button type="button" className="secondary-button" onClick={leaveUnsubmittedSet}>放弃本组并返回</button>
            <button type="button" className="primary-button" disabled={submitting} onClick={() => void submit()}>{submitting ? "正在判分…" : `提交本组（${answeredCount}/${trainingSet.items.length}）`}</button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="page-wrap ability-page">
      <header className="page-heading">
        <p className="eyebrow">CORE ABILITIES & QUESTION TYPES</p>
        <h1>阅读专项训练中心</h1>
        <p>这里负责用真实题训练和判分，不重复展示方法课程。7种基础能力和17种具体题型共用同一套真实题生成、服务端判分和错题闭环；题目不会由AI编造。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="ability-policy-strip">
        <div><span>基础能力</span><strong>7种</strong></div>
        <div><span>具体题型</span><strong>17种</strong></div>
        <div><span>题目来源</span><strong>真实题库</strong></div>
        <div><span>训练AI调用</span><strong>0</strong></div>
      </section>

      <div className="method-tabs" role="tablist" aria-label="专项训练分类">
        <button
          type="button"
          role="tab"
          aria-selected={catalogMode === "ability"}
          className={catalogMode === "ability" ? "active" : ""}
          onClick={() => {
            setCatalogMode("ability");
            if (!skills.some((item) => item.id === activeSkillId)) setActiveSkillId(skills[0]?.id || "");
          }}
        >7种基础能力</button>
        <button
          type="button"
          role="tab"
          aria-selected={catalogMode === "question_type"}
          className={catalogMode === "question_type" ? "active" : ""}
          onClick={() => {
            setCatalogMode("question_type");
            if (!questionTypes.some((item) => item.id === activeSkillId)) setActiveSkillId(questionTypes[0]?.id || "");
          }}
        >17种题型专项</button>
      </div>

      {loading ? <div className="ability-loading">正在统计真实题库…</div> : (
        <div className="ability-skill-grid">
          {visibleTargets.map((skill, index) => (
            <article className={skill.id === activeSkillId ? "ability-skill-card active" : "ability-skill-card"} key={skill.id}>
              <div className="ability-skill-number">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <span>{catalogMode === "ability" ? "CORE SKILL" : "QUESTION TYPE"}</span>
                <h2>{skill.label}</h2>
                <p>{skill.objective}</p>
              </div>
              <div className="ability-skill-footer">
                <small>可用真实题 {skill.available_questions} 道</small>
                <button
                  type="button"
                  className="primary-button"
                  disabled={generating || skill.available_questions === 0}
                  onClick={() => void loadSet(skill.id, 0, [], trainingMode)}
                >{skill.available_questions === 0 ? "暂无可用真题" : "开始8题训练"}</button>
              </div>
            </article>
          ))}
        </div>
      )}
      <section className="ability-review-note">
        <div><h2>从错题进入更精准</h2><p>错题中心会根据具体题型和错误类型，自动推荐最相关的能力训练。</p></div>
        <Link href="/review" className="secondary-button">查看我的错题</Link>
      </section>
    </div>
  );
}

function AbilityQuestionCard({
  item,
  index,
  value,
  disabled,
  result,
  onChange
}: {
  item: AbilityQuestionItem;
  index: number;
  value: AnswerValue | undefined;
  disabled: boolean;
  result?: ScoringResult["question_results"][number];
  onChange: (value: AnswerValue) => void;
}) {
  const group = item.group;
  const question = group.questions[0];
  const subtype = group.question_subtype || group.question_type;
  const options = optionsFor(group, question);
  const judgement = subtype === "true_false_not_given"
    ? ["TRUE", "FALSE", "NOT GIVEN"]
    : subtype === "yes_no_not_given"
      ? ["YES", "NO", "NOT GIVEN"]
      : null;
  const multi = subtype === "multiple_choice_multiple" || Number(group.required_choices || 1) > 1;
  const choice = subtype === "multiple_choice_single";

  return (
    <article
      className={result ? (result.is_correct ? "ability-question-card correct" : "ability-question-card wrong") : "ability-question-card"}
      data-ability-question-id={item.ref_id}
    >
      <div className="ability-source-head">
        <div><span>真实题 {index + 1}</span><strong>{item.test_title} · Part {item.part_number}</strong></div>
        <small>{group.question_label || subtype}</small>
      </div>
      <details className="ability-passage" open={index === 0}>
        <summary>查看本题原文：{item.passage.article_title || item.passage.title}</summary>
        <div>{item.passage.paragraphs.map((paragraph, paragraphIndex) => <p key={`${paragraph.index ?? paragraphIndex}-${paragraph.text.slice(0, 16)}`}><b>{paragraph.label}</b>{paragraph.text}</p>)}</div>
      </details>
      <div className="ability-question-copy">
        <p className="ability-instructions">{group.instructions}</p>
        <div><span className="question-number">{question.display_number ?? question.number}</span><strong>{repairDisplayText(question.prompt)}</strong></div>
      </div>

      {judgement ? (
        <div className="ability-answer-options judgement-options">
          {judgement.map((option) => <label key={option} className={value === option ? "selected" : ""}><input disabled={disabled} type="radio" name={`ability-${item.ref_id}`} checked={value === option} onChange={() => onChange(option)} /><span>{option}</span></label>)}
        </div>
      ) : multi && options.length ? (
        <div className="ability-answer-options">
          {options.map((option) => {
            const selected = Array.isArray(value) && value.includes(option.code);
            return <label key={option.code} className={selected ? "selected" : ""}><input disabled={disabled} type="checkbox" checked={selected} onChange={() => {
              const current = Array.isArray(value) ? value : [];
              if (selected) onChange(current.filter((itemValue) => itemValue !== option.code));
              else if (current.length < Number(group.required_choices || 2)) onChange([...current, option.code]);
            }} /><b>{option.code}</b><span>{repairDisplayText(option.text)}</span></label>;
          })}
        </div>
      ) : options.length && (choice || subtype.startsWith("matching_")) ? (
        <label className="ability-select-answer"><span>选择答案</span><select disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}><option value="">请选择</option>{options.map((option) => <option key={option.code} value={option.code}>{option.code} · {repairDisplayText(option.text)}</option>)}</select></label>
      ) : (
        <label className="ability-text-answer"><span>填写答案</span><input disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} autoComplete="off" spellCheck={false} /></label>
      )}

      {result ? (
        <div className={result.is_correct ? "ability-feedback correct" : "ability-feedback wrong"}>
          <strong>{result.is_correct ? "回答正确" : "需要复盘"} · 用时 {formatSeconds(result.elapsed_seconds || 0)}</strong>
          {!result.is_correct ? <p>你的答案：{result.user_answer || "未作答"}　正确答案：{result.correct_answer}</p> : null}
          {result.answer_error_type === "word_limit_exceeded" ? <p>答案超过词数限制。</p> : null}
          {result.answer_error_type === "answer_span_too_long" ? <p>答案边界过长。</p> : null}
          {result.answer_error_type === "answer_span_too_short" ? <p>答案边界过短。</p> : null}
          {result.analysis || result.reason ? <p>{repairDisplayText(String(result.analysis || result.reason || ""))}</p> : null}
          {result.evidence?.length ? <blockquote>{result.evidence.join("\n")}</blockquote> : null}
        </div>
      ) : null}
    </article>
  );
}
