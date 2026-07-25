"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchAbilitySkills,
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
  if (group.normalized_options?.length) return group.normalized_options;
  const raw = question.options?.length
    ? question.options
    : Array.isArray(group.shared_options) && group.shared_options.length
      ? group.shared_options
      : group.options || [];
  return raw.map(normalizeOption).filter((item): item is QuestionOption => Boolean(item));
}

function formatSeconds(value: number): string {
  const minutes = Math.floor(Math.max(0, value) / 60);
  const seconds = Math.max(0, value) % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function AbilityTrainingCenter() {
  const [skills, setSkills] = useState<AbilitySkill[]>([]);
  const [activeSkillId, setActiveSkillId] = useState("");
  const [trainingSet, setTrainingSet] = useState<AbilitySet | null>(null);
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [result, setResult] = useState<ScoringResult | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [clientSubmissionId, setClientSubmissionId] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchAbilitySkills(controller.signal)
      .then((items) => {
        setSkills(items);
        const querySkill = new URLSearchParams(window.location.search).get("skill") || "";
        const selected = items.find((item) => item.id === querySkill) || items[0];
        if (selected) setActiveSkillId(selected.id);
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
  }, []);

  useEffect(() => {
    if (!trainingSet || result) return;
    const timer = window.setInterval(() => setElapsedSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [trainingSet, result]);

  const activeSkill = skills.find((skill) => skill.id === activeSkillId);
  const answeredCount = useMemo(() => {
    if (!trainingSet) return 0;
    return trainingSet.items.filter((item) => {
      const value = answers[item.ref_id];
      return Array.isArray(value) ? value.length > 0 : Boolean(String(value || "").trim());
    }).length;
  }, [answers, trainingSet]);

  async function loadSet(skillId: string, cursor = 0) {
    setGenerating(true);
    setError("");
    try {
      const generated = await generateAbilitySet(skillId, 8, cursor);
      setTrainingSet(generated);
      setAnswers({});
      setResult(null);
      setElapsedSeconds(0);
      setClientSubmissionId(newSubmissionId());
      setActiveSkillId(skillId);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "训练题生成失败");
    } finally {
      setGenerating(false);
    }
  }

  async function submit() {
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
        elapsed_seconds: elapsedSeconds
      });
      setResult(response.result);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "能力训练提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (trainingSet) {
    return (
      <div className="page-wrap ability-session-page">
        <header className="ability-session-head">
          <div>
            <p className="eyebrow">VERIFIED QUESTION TRAINING</p>
            <h1>{trainingSet.skill.label}能力训练</h1>
            <p>{trainingSet.skill.objective}</p>
          </div>
          <div className="ability-session-meta">
            <span>真实题库</span><strong>{trainingSet.items.length}题</strong>
            <span>用时</span><strong>{formatSeconds(elapsedSeconds)}</strong>
          </div>
        </header>
        {error ? <div className="page-error">{error}</div> : null}

        {result ? (
          <section className="ability-result-panel">
            <div className="ability-result-score"><span>本组成绩</span><strong>{result.score}/{result.total}</strong><small>{result.accuracy}%</small></div>
            <div>
              <h2>{result.score === result.total ? "本组全部答对" : `需要复盘 ${result.wrong_questions.length} 题`}</h2>
              <p>能力训练不是完整40题，因此不会显示Band。结果已经保存到Session和错题库。</p>
            </div>
            <div className="ability-result-actions">
              <button type="button" className="secondary-button" onClick={() => setTrainingSet(null)}>返回能力列表</button>
              <button type="button" className="primary-button" onClick={() => void loadSet(trainingSet.skill.id, trainingSet.next_cursor)}>换一组真实题</button>
            </div>
          </section>
        ) : (
          <div className="ability-progress-bar"><span style={{ width: `${trainingSet.items.length ? answeredCount / trainingSet.items.length * 100 : 0}%` }} /><strong>{answeredCount}/{trainingSet.items.length} 已作答</strong></div>
        )}

        <div className="ability-question-list">
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
                onChange={(value) => setAnswers((current) => ({ ...current, [item.ref_id]: value }))}
              />
            );
          })}
        </div>
        {!result ? (
          <div className="ability-submit-bar">
            <button type="button" className="secondary-button" onClick={() => setTrainingSet(null)}>保存记录并返回</button>
            <button type="button" className="primary-button" disabled={submitting} onClick={() => void submit()}>{submitting ? "正在判分…" : `提交本组（${answeredCount}/${trainingSet.items.length}）`}</button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="page-wrap ability-page">
      <header className="page-heading">
        <p className="eyebrow">SEVEN CORE ABILITIES</p>
        <h1>阅读基础能力训练</h1>
        <p>七种能力全部从46套已迁入、已通过SHA-256校验的真实题库中选题。系统不会用AI编造练习题，所有提交由服务端确定性判分。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="ability-policy-strip">
        <div><span>训练能力</span><strong>7种</strong></div>
        <div><span>题目来源</span><strong>真实题库</strong></div>
        <div><span>训练AI调用</span><strong>0</strong></div>
        <div><span>判分方式</span><strong>服务端规则</strong></div>
      </section>

      {loading ? <div className="ability-loading">正在统计真实题库…</div> : (
        <div className="ability-skill-grid">
          {skills.map((skill, index) => (
            <article className={skill.id === activeSkillId ? "ability-skill-card active" : "ability-skill-card"} key={skill.id}>
              <div className="ability-skill-number">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <span>CORE SKILL</span>
                <h2>{skill.label}</h2>
                <p>{skill.objective}</p>
              </div>
              <div className="ability-skill-footer">
                <small>可用真实题 {skill.available_questions} 道</small>
                <button type="button" className="primary-button" disabled={generating} onClick={() => void loadSet(skill.id, 0)}>开始8题训练</button>
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
    <article className={result ? (result.is_correct ? "ability-question-card correct" : "ability-question-card wrong") : "ability-question-card"}>
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
        <div><span className="question-number">{question.display_number ?? question.number}</span><strong>{question.prompt}</strong></div>
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
            }} /><b>{option.code}</b><span>{option.text}</span></label>;
          })}
        </div>
      ) : options.length && (choice || subtype.startsWith("matching_")) ? (
        <label className="ability-select-answer"><span>选择答案</span><select disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)}><option value="">请选择</option>{options.map((option) => <option key={option.code} value={option.code}>{option.code} · {option.text}</option>)}</select></label>
      ) : (
        <label className="ability-text-answer"><span>填写答案</span><input disabled={disabled} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} autoComplete="off" spellCheck={false} /></label>
      )}

      {result ? (
        <div className={result.is_correct ? "ability-feedback correct" : "ability-feedback wrong"}>
          <strong>{result.is_correct ? "回答正确" : "需要复盘"}</strong>
          {!result.is_correct ? <p>你的答案：{result.user_answer || "未作答"}　正确答案：{result.correct_answer}</p> : null}
          {result.answer_error_type === "word_limit_exceeded" ? <p>答案超过词数限制。</p> : null}
          {result.answer_error_type === "answer_span_too_long" ? <p>答案边界过长。</p> : null}
          {result.answer_error_type === "answer_span_too_short" ? <p>答案边界过短。</p> : null}
          {result.analysis || result.reason ? <p>{result.analysis || result.reason}</p> : null}
          {result.evidence?.length ? <blockquote>{result.evidence.join("\n")}</blockquote> : null}
        </div>
      ) : null}
    </article>
  );
}
