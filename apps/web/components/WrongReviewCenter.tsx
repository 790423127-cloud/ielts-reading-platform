"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchWrongQuestions, type WrongReviewItem } from "@/lib/api";

const USER_ID = "owner";

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

      {loading ? <div className="review-empty">正在读取练习记录…</div> : filtered.length ? (
        <div className="wrong-review-list">
          {filtered.map((item) => (
            <article className="wrong-review-card" key={`${item.source_session_id}-${item.id}`}>
              <div className="wrong-review-head">
                <div>
                  <span>Q{item.number} · {item.question_type}</span>
                  <h2>{item.prompt}</h2>
                  <small>{item.source_test_id} · Part {item.part_number} · {formatDate(item.last_attempt_at)}</small>
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
              <div className="review-route-panel">
                <div><span>系统建议能力</span><strong>{item.recommended_skill_label}</strong></div>
                <div className="review-route-actions">
                  <Link className="secondary-button" href={`/methods?course=${encodeURIComponent(item.method_course_id)}`}>学习对应方法</Link>
                  <Link className="primary-button" href={`/ability?skill=${encodeURIComponent(item.recommended_skill_id)}`}>做能力训练</Link>
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
