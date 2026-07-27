"use client";

import { useEffect, useMemo, useState } from "react";

import {
  archiveSession,
  fetchSession,
  fetchSessions,
  restoreSession,
  type ScoringResult,
  type SessionSummary
} from "@/lib/api";

function dateText(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"
  }).format(new Date(value));
}

function downloadJson(session: SessionSummary, result: ScoringResult) {
  const blob = new Blob([JSON.stringify({ session, result }, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${session.test_id}-${session.created_at.slice(0, 10)}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function HistoryCenter() {
  const [items, setItems] = useState<SessionSummary[]>([]);
  const [mode, setMode] = useState("all");
  const [query, setQuery] = useState("");
  const [recordStatus, setRecordStatus] = useState<"active" | "archived" | "all">("active");
  const [detail, setDetail] = useState<{ summary: SessionSummary; result: ScoringResult } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      setItems(await fetchSessions("owner", undefined, true));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "练习记录读取失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const modes = useMemo(() => [...new Set(items.map((item) => item.exam_mode))], [items]);
  const filtered = useMemo(() => items.filter((item) => {
    const modeMatch = mode === "all" || item.exam_mode === mode;
    const queryMatch = !query || `${item.test_title} ${item.test_id}`.toLowerCase().includes(query.toLowerCase());
    const statusMatch = recordStatus === "all" || (recordStatus === "archived" ? item.archived : !item.archived);
    return modeMatch && queryMatch && statusMatch;
  }), [items, mode, query, recordStatus]);

  async function open(summary: SessionSummary) {
    setError("");
    try {
      const row = await fetchSession(summary.session_id);
      setDetail({ summary, result: row.result });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "记录详情读取失败");
    }
  }

  async function archive(summary: SessionSummary) {
    if (!window.confirm("把这条记录移入归档吗？归档不会永久删除数据。")) return;
    try {
      await archiveSession(summary.session_id);
      setDetail(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "归档失败");
    }
  }

  async function restore(summary: SessionSummary) {
    try {
      await restoreSession(summary.session_id);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复记录失败");
    }
  }

  return (
    <section className="page-wrap history-page">
      <header className="page-heading">
        <p className="eyebrow">PRACTICE HISTORY</p>
        <h1>练习记录中心</h1>
        <p>集中查看完整模考、Part、题型和错题再练记录。归档采用可恢复方式，不执行永久删除。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <div className="history-toolbar">
        <input aria-label="搜索套题" placeholder="搜索套题名称" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="按训练模式筛选" value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="all">全部模式（{items.length}）</option>
          {modes.map((value) => <option value={value} key={value}>{value}（{items.filter((item) => item.exam_mode === value).length}）</option>)}
        </select>
        <select aria-label="按记录状态筛选" value={recordStatus} onChange={(event) => setRecordStatus(event.target.value as typeof recordStatus)}>
          <option value="active">正常记录</option><option value="archived">已归档</option><option value="all">全部状态</option>
        </select>
      </div>
      {loading ? <div className="review-empty">正在读取记录…</div> : filtered.length ? (
        <div className="history-table-wrap">
          <table className="history-table">
            <thead><tr><th>时间</th><th>练习</th><th>模式</th><th>成绩</th><th>Band</th><th>操作</th></tr></thead>
            <tbody>{filtered.map((item) => (
              <tr key={item.session_id}>
                <td>{dateText(item.created_at)}</td><td><strong>{item.test_title}</strong><small>{item.test_id}</small></td>
                <td>{item.exam_mode}</td><td>{item.score}/{item.total} · {item.accuracy}%</td>
                <td>{item.estimated_band == null ? "不适用" : item.estimated_band.toFixed(1)}</td>
                <td><button className="secondary-button" type="button" onClick={() => void open(item)}>查看详情</button>{item.archived ? <button className="secondary-button" type="button" onClick={() => void restore(item)}>恢复</button> : null}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      ) : <div className="review-empty">当前筛选下没有记录。</div>}

      {detail ? (
        <div className="system-modal-backdrop" role="presentation" onMouseDown={() => setDetail(null)}>
          <section className="system-modal history-detail" role="dialog" aria-modal="true" aria-label="练习详情" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><span>{dateText(detail.summary.created_at)}</span><h2>{detail.summary.test_title}</h2></div><button type="button" onClick={() => setDetail(null)}>关闭</button></header>
            <div className="history-detail-metrics">
              <article><span>成绩</span><strong>{detail.result.score}/{detail.result.total}</strong></article>
              <article><span>正确率</span><strong>{detail.result.accuracy}%</strong></article>
              <article><span>未作答</span><strong>{detail.result.unanswered_count}</strong></article>
              <article><span>用时</span><strong>{Math.round(detail.result.total_elapsed_seconds / 60)} 分钟</strong></article>
            </div>
            <h3>Part 明细</h3>
            <div className="history-part-list">{detail.result.part_results.map((part) => (
              <div key={part.part_number}><strong>Part {part.part_number}</strong><span>{part.score}/{part.total} · {part.accuracy}%</span></div>
            ))}</div>
            <footer>
              <button className="secondary-button danger-text" type="button" onClick={() => void archive(detail.summary)}>移入归档</button>
              <button className="primary-button" type="button" onClick={() => downloadJson(detail.summary, detail.result)}>导出 JSON</button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
