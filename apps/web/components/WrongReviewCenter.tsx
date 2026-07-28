"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchWrongQuestions,
  saveWrongQuestionFeedback,
  type WrongReviewItem
} from "@/lib/api";

const USER_ID = "owner";
const CAUSE_OPTIONS = [
  ["unknown_vocabulary", "不认识关键词"],
  ["paraphrase_failure", "没识别同义替换"],
  ["sentence_structure", "句子结构没看懂"],
  ["false_vs_not_given", "FALSE/NO 与 NOT GIVEN 混淆"],
  ["true_vs_not_given", "TRUE/YES 与 NOT GIVEN 混淆"],
  ["unsupported_inference", "做了原文不支持的推断"],
  ["scope_expansion", "把部分扩大成全部"],
  ["keyword_distractor", "被相同关键词干扰"],
  ["word_limit_exceeded", "超过词数限制"],
  ["spelling_error", "拼写错误"],
  ["singular_plural_error", "单复数错误"],
  ["instruction_misread", "看错题目要求"],
  ["location_failure", "没有正确定位"],
  ["time_pressure", "时间不够"],
  ["other", "其他原因"]
] as const;

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export default function WrongReviewCenter() {
  const [items, setItems] = useState<WrongReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [subtype, setSubtype] = useState("all");
  const [batchCount, setBatchCount] = useState(10);
  const [batchPart, setBatchPart] = useState("all");
  const [batchMode, setBatchMode] = useState<"free" | "timed">("free");

  useEffect(() => {
    const controller = new AbortController();
    fetchWrongQuestions(USER_ID, controller.signal)
      .then(setItems)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "错题读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const subtypes = useMemo(
    () => [...new Set(items.map((item) => item.question_subtype))].sort(),
    [items]
  );
  const filtered = useMemo(
    () => subtype === "all" ? items : items.filter((item) => item.question_subtype === subtype),
    [items, subtype]
  );
  const repeatedWrong = items.filter((item) => item.wrong_count >= 2).length;
  const oneMoreCorrect = items.filter((item) => item.correct_streak_after_wrong === 1).length;
  const batchCandidates = items.filter((item) => batchPart === "all" || String(item.source_part_number) === batchPart);
  const batchRefs = batchCandidates.slice(0, batchCount).map((item) => item.source_question_ref);
  const batchHref = `/ability?skill=wrong-batch&questions=${encodeURIComponent(batchRefs.join(","))}&mode=${batchMode}`;

  return (
    <div className="page-wrap review-center-page">
      <header className="page-heading">
        <p className="eyebrow">DETERMINISTIC REVIEW</p>
        <h1>错题复盘中心</h1>
        <p>错题直接来自服务端Session。看过解析不会自动移除；最近一次错误后必须连续答对两次，才视为完成验证。</p>
      </header>

      {error ? <div className="page-error">{error}</div> : null}
      <section className="review-stat-strip">
        <article><span>待复习错题</span><strong>{items.length}</strong></article>
        <article><span>重复做错</span><strong>{repeatedWrong}</strong></article>
        <article><span>再答对1次移出</span><strong>{oneMoreCorrect}</strong></article>
        <article><span>移出规则</span><strong>连续2次</strong></article>
      </section>

      <div className="review-toolbar">
        <label>
          <span>按具体题型筛选</span>
          <select value={subtype} onChange={(event) => setSubtype(event.target.value)}>
            <option value="all">全部题型</option>
            {subtypes.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <Link href="/practice" className="secondary-button">进入题库做新题验证</Link>
      </div>
      <section className="wrong-batch-setup">
        <div><p className="eyebrow">WRONG QUESTION BATCH</p><h2>错题批量再练</h2><p>按最近仍未移出闭环的错题组卷，服务端会逐题回查权威题库。</p></div>
        <label><span>题量</span><select value={batchCount} onChange={(event) => setBatchCount(Number(event.target.value))}>{[5,10,15,20].map((count) => <option key={count} value={count}>{count} 题</option>)}</select></label>
        <label><span>Part 范围</span><select value={batchPart} onChange={(event) => setBatchPart(event.target.value)}><option value="all">全部 Part</option><option value="1">Part 1</option><option value="2">Part 2</option><option value="3">Part 3</option></select></label>
        <label><span>训练模式</span><select value={batchMode} onChange={(event) => setBatchMode(event.target.value as "free" | "timed")}><option value="free">自由模式</option><option value="timed">计时模式</option></select></label>
        {batchRefs.length ? <Link className="primary-button" href={batchHref}>开始再练 {batchRefs.length} 题</Link> : <button className="primary-button" type="button" disabled>当前范围无错题</button>}
      </section>

      {loading ? <div className="review-empty">正在读取练习记录…</div> : filtered.length ? (
        <div className="wrong-review-list">
          {filtered.map((item) => (
            <article className="wrong-review-card" key={`${item.source_session_id}-${item.id}`}>
              <div className="wrong-review-head">
                <div>
                  <span>Q{item.number} · {item.question_type}</span>
                  <h2>{item.prompt}</h2>
                  <small>{item.source_test_id} · Part {item.source_part_number} · {formatDate(item.last_attempt_at)}</small>
                </div>
                <div className="review-status">
                  <strong>错 {item.wrong_count} 次</strong>
                  <span>错误后连续答对 {item.correct_streak_after_wrong}/2</span>
                </div>
              </div>
              <div className="review-answer-row">
                <span>你的答案：<b>{item.user_answer || "未作答"}</b></span>
                <span>正确答案：<b>{item.correct_answer}</b></span>
              </div>
              {item.answer_error_type === "word_limit_exceeded" ? <div className="review-warning">答案超过题目词数限制。</div> : null}
              {item.answer_error_type === "answer_span_too_long" ? <div className="review-warning">定位基本正确，但答案边界过长。</div> : null}
              {item.answer_error_type === "answer_span_too_short" ? <div className="review-warning">答案缺少构成完整含义的必要词。</div> : null}
              {item.analysis || item.reason ? <p className="review-analysis">{item.analysis || item.reason}</p> : null}
              {item.paraphrasing ? <p className="review-paraphrase"><b>同义替换：</b>{item.paraphrasing}</p> : null}
              {item.evidence?.length ? <blockquote>{item.evidence.join("\n")}</blockquote> : <div className="review-warning">题库中没有经过核验的定位句，不会由AI补造证据。</div>}
              <WrongCauseFeedback
                item={item}
                onSaved={(feedback) => {
                  setItems((current) => current.map((row) => (
                    row.source_session_id === item.source_session_id && row.id === item.id
                      ? { ...row, student_feedback: feedback }
                      : row
                  )));
                }}
              />
              <div className="review-route-panel">
                <div><span>系统建议能力</span><strong>{item.recommended_skill_label}</strong></div>
                <div className="review-route-actions">
                  <Link
                    className="primary-button"
                    href={`/ability?subtype=${encodeURIComponent(item.question_subtype)}&question=${encodeURIComponent(item.source_question_ref)}`}
                  >返回原题重做</Link>
                  <Link className="secondary-button" href={`/methods?course=${encodeURIComponent(item.method_course_id)}`}>学习对应方法</Link>
                  <Link className="secondary-button" href={`/ability?skill=${encodeURIComponent(item.recommended_skill_id)}`}>做能力训练</Link>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="review-empty">
          <strong>{items.length ? "当前筛选下没有错题" : "当前没有待复习错题"}</strong>
          <p>完成题库练习后，做错的题会自动进入这里；连续答对两次后自动移出。</p>
          <Link className="primary-button" href="/practice">开始一次练习</Link>
        </div>
      )}
    </div>
  );
}

function WrongCauseFeedback({
  item,
  onSaved
}: {
  item: WrongReviewItem;
  onSaved: (feedback: NonNullable<WrongReviewItem["student_feedback"]>) => void;
}) {
  const existing = item.student_feedback;
  const [open, setOpen] = useState(Boolean(existing));
  const [matchStatus, setMatchStatus] = useState<"matches" | "partial" | "does_not_match">(
    existing?.match_status || "matches"
  );
  const [understanding, setUnderstanding] = useState<"understood" | "needs_review">(
    existing?.understanding_status || "needs_review"
  );
  const [causeId, setCauseId] = useState(existing?.cause_id || "");
  const [note, setNote] = useState(existing?.note || "");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");

  async function save() {
    setSaving(true);
    setStatus("");
    try {
      const feedback = await saveWrongQuestionFeedback(item, {
        match_status: matchStatus,
        understanding_status: understanding,
        cause_id: causeId || null,
        note
      });
      onSaved(feedback);
      setStatus("已保存。你的确认会优先于 AI 对错因的推测。");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "错因确认保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={open ? "wrong-cause-feedback open" : "wrong-cause-feedback"}>
      <button className="wrong-cause-toggle" type="button" onClick={() => setOpen((value) => !value)}>
        <span>
          <strong>{existing ? "已确认错因" : "确认我为什么做错"}</strong>
          <small>这是你的学习记录，不会改变标准答案、判分或题库解析。</small>
        </span>
        <b>{open ? "收起" : "填写"}</b>
      </button>
      {open ? (
        <div className="wrong-cause-form">
          <fieldset>
            <legend>系统分析是否符合你的实际情况？</legend>
            <label><input type="radio" name={`match-${item.source_session_id}-${item.id}`} checked={matchStatus === "matches"} onChange={() => setMatchStatus("matches")} />符合</label>
            <label><input type="radio" name={`match-${item.source_session_id}-${item.id}`} checked={matchStatus === "partial"} onChange={() => setMatchStatus("partial")} />部分符合</label>
            <label><input type="radio" name={`match-${item.source_session_id}-${item.id}`} checked={matchStatus === "does_not_match"} onChange={() => setMatchStatus("does_not_match")} />不符合</label>
          </fieldset>
          <fieldset>
            <legend>现在是否已经理解？</legend>
            <label><input type="radio" name={`understanding-${item.source_session_id}-${item.id}`} checked={understanding === "understood"} onChange={() => setUnderstanding("understood")} />已理解</label>
            <label><input type="radio" name={`understanding-${item.source_session_id}-${item.id}`} checked={understanding === "needs_review"} onChange={() => setUnderstanding("needs_review")} />仍需复习</label>
          </fieldset>
          <label className="wrong-cause-select">
            <span>我确认的主要错因</span>
            <select value={causeId} onChange={(event) => setCauseId(event.target.value)}>
              <option value="">暂不选择</option>
              {CAUSE_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="wrong-cause-note">
            <span>补充说明（可选）</span>
            <textarea value={note} maxLength={2000} onChange={(event) => setNote(event.target.value)} placeholder="例如：定位到了正确段落，但把 only 看漏了。" />
          </label>
          <div className="wrong-cause-actions">
            <button className="primary-button" type="button" disabled={saving} onClick={() => void save()}>
              {saving ? "保存中…" : "保存我的确认"}
            </button>
            {status ? <span>{status}</span> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
