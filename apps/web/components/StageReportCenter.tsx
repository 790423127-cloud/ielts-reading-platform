"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  fetchStageReport,
  stageReportDownloadUrl,
  type StageReport,
  type TimedQuestionReportItem
} from "@/lib/api";

function formatDate(value?: string | null): string {
  if (!value) return "暂无";
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "numeric",
      day: "numeric"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours}小时${minutes % 60}分` : `${minutes}分钟`;
}

function formatQuestionTime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const remainder = safe % 60;
  return minutes ? `${minutes}分${String(remainder).padStart(2, "0")}秒` : `${remainder}秒`;
}

function TimedQuestionList({
  items,
  emptyText
}: {
  items: TimedQuestionReportItem[];
  emptyText: string;
}) {
  if (!items.length) return <div className="report-timing-empty">{emptyText}</div>;
  return (
    <div className="report-timing-list">
      {items.map((item, index) => (
        <article key={`${item.source_question_ref}-${item.created_at}`}>
          <span className="report-timing-rank">{index + 1}</span>
          <div>
            <small>{item.test_title} · Q{item.question_number} · {item.question_type}</small>
            <strong>{item.prompt}</strong>
            <span>你的答案：{item.user_answer || "未作答"} · 正确答案：{item.correct_answer}</span>
          </div>
          <div className="report-timing-value">
            <strong>{formatQuestionTime(item.elapsed_seconds)}</strong>
            {item.source_question_ref ? (
              <Link href={`/ability?subtype=${encodeURIComponent(item.question_subtype)}&question=${encodeURIComponent(item.source_question_ref)}`}>
                返回原题
              </Link>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  );
}

export default function StageReportCenter() {
  const [report, setReport] = useState<StageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchStageReport("owner", controller.signal)
      .then(setReport)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "阶段报告读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="page-wrap stage-report-page">
      <header className="page-heading stage-report-heading">
        <div>
          <p className="eyebrow">DETERMINISTIC STAGE REPORT</p>
          <h1>阶段学习报告</h1>
          <p>直接汇总新版已保存的Session、题型表现和代表错题。报告不调用AI，不修改成绩，首次练习与相同配置重做分开标记。</p>
        </div>
        <div className="teacher-report-downloads">
          {report?.summary.session_count ? (
            <>
              <a className="primary-button" href={stageReportDownloadUrl("pdf")}>下载正式 PDF</a>
              <a className="secondary-button" href={stageReportDownloadUrl("docx")}>下载 DOCX</a>
            </>
          ) : null}
          <button
            type="button"
            className="secondary-button report-print-button"
            disabled={!report?.summary.session_count}
            onClick={() => window.print()}
          >打印</button>
        </div>
      </header>

      {error ? <div className="page-error">{error}</div> : null}
      {loading ? <div className="report-empty">正在汇总已保存的学习记录…</div> : report?.summary.session_count ? (
        <>
          <section className="report-cover-card">
            <div>
              <span>REPORT PERIOD</span>
              <strong>{formatDate(report.summary.date_from)} — {formatDate(report.summary.date_to)}</strong>
              <small>引擎 {report.engine_version} · AI调用 {report.ai_calls} 次</small>
            </div>
            <article><span>练习记录</span><strong>{report.summary.session_count}</strong><small>首次 {report.summary.first_attempt_count} · 重做 {report.summary.retry_count}</small></article>
            <article><span>累计正确率</span><strong>{report.summary.accuracy}%</strong><small>{report.summary.correct}/{report.summary.total_questions}题</small></article>
            <article><span>累计用时</span><strong>{formatTime(report.summary.total_elapsed_seconds)}</strong><small>以已提交Session为准</small></article>
          </section>

          <section className="report-section">
            <div className="report-section-title"><span>01</span><div><h2>确定性结论</h2><p>只描述当前数据能支持的事实。</p></div></div>
            <ul className="report-insights">
              {report.deterministic_interpretation.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section className="report-section">
            <div className="report-section-title"><span>02</span><div><h2>题型表现矩阵</h2><p>少于5题不定性，5–9题为初步倾向，10题以上为较稳定样本。</p></div></div>
            <div className="report-type-table" role="table" aria-label="题型表现">
              <div className="report-table-head" role="row"><span>题型</span><span>正确</span><span>正确率</span><span>判断</span></div>
              {report.question_type_matrix.map((item) => (
                <div role="row" key={item.question_subtype}>
                  <strong>{item.question_type}</strong>
                  <span>{item.correct}/{item.total}</span>
                  <span>{item.accuracy}%</span>
                  <span className={`report-status ${item.status}`}>{item.status_label}</span>
                </div>
              ))}
            </div>
          </section>

          <section className="report-section">
            <div className="report-section-title"><span>03</span><div><h2>练习趋势</h2><p>相同配置的后续记录标为重做，避免和首次作答混在一起。</p></div></div>
            <div className="report-trend-grid">
              {report.trend.map((item) => (
                <article key={item.session_id}>
                  <div><span>{formatDate(item.created_at)}</span><b>{item.attempt_kind === "first" ? "首次" : `重做 ${item.attempt_number - 1}`}</b></div>
                  <h3>{item.skill_label || item.test_title}</h3>
                  <strong>{item.score}/{item.total}</strong>
                  <small>{item.accuracy}% · {formatTime(item.elapsed_seconds)}</small>
                </article>
              ))}
            </div>
          </section>

          <section className="report-section">
            <div className="report-section-title"><span>04</span><div><h2>单题用时</h2><p>按实际停留时间排序；正确题展示最耗时的3道，错误题展示最耗时的5道。</p></div></div>
            <div className="report-timing-grid">
              <section>
                <header><span>回答正确</span><strong>最耗时 3 题</strong></header>
                <TimedQuestionList
                  items={report.slowest_correct_questions || []}
                  emptyText="新提交记录中还没有带单题用时的正确题。"
                />
              </section>
              <section>
                <header><span>回答错误</span><strong>最耗时 5 题</strong></header>
                <TimedQuestionList
                  items={report.slowest_wrong_questions || []}
                  emptyText="新提交记录中还没有带单题用时的错误题。"
                />
              </section>
            </div>
          </section>

          <section className="report-section">
            <div className="report-section-title"><span>05</span><div><h2>代表错题</h2><p>优先显示最近且来源不重复的错题，可直接回到同一道真实原题。</p></div></div>
            {report.representative_questions.length ? (
              <div className="report-question-list">
                {report.representative_questions.map((item) => (
                  <article key={`${item.source_question_ref}-${item.created_at}`}>
                    <div><span>{item.test_title} · Q{item.question_number}</span><strong>{item.question_type}</strong></div>
                    <h3>{item.prompt}</h3>
                    <p>你的答案：<b>{item.user_answer}</b>　正确答案：<b>{item.correct_answer}</b></p>
                    {item.analysis ? <p>{item.analysis}</p> : null}
                    {item.evidence.length ? <blockquote>{item.evidence.join("\n")}</blockquote> : null}
                    {item.source_question_ref ? (
                      <Link
                        className="secondary-button"
                        href={`/ability?subtype=${encodeURIComponent(item.question_subtype)}&question=${encodeURIComponent(item.source_question_ref)}`}
                      >返回原题重做</Link>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : <div className="report-empty">当前记录中没有错题。</div>}
          </section>

          <section className="report-notes">
            <h2>报告边界</h2>
            <ul>{report.data_notes.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        </>
      ) : (
        <div className="report-empty">
          <strong>还没有可生成报告的已提交练习</strong>
          <p>先完成一次整套、单Part、能力或题型专项，系统会自动用Session生成阶段报告。</p>
          <Link href="/practice" className="primary-button">开始练习</Link>
        </div>
      )}
    </div>
  );
}
