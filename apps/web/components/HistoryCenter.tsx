"use client";

import { useEffect, useMemo, useState } from "react";

import {
  deleteSession,
  deleteSessions,
  fetchSession,
  fetchSessions,
  restoreSession,
  sessionReportDownloadUrl,
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

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
  const selectableFiltered = filtered;
  const allVisibleSelected = selectableFiltered.length > 0
    && selectableFiltered.every((item) => selectedIds.has(item.session_id));

  async function open(summary: SessionSummary) {
    setError("");
    try {
      const row = await fetchSession(summary.session_id);
      setDetail({ summary, result: row.result });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "记录详情读取失败");
    }
  }

  function openDetailedReport(summary: SessionSummary) {
    window.location.assign(`/practice?session=${encodeURIComponent(summary.session_id)}`);
  }

  async function remove(summary: SessionSummary) {
    if (!window.confirm("确定永久删除这条练习记录吗？删除后无法恢复。")) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await deleteSession(summary.session_id);
      setItems((current) => current.filter((item) => item.session_id !== summary.session_id));
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(summary.session_id);
        return next;
      });
      if (detail?.summary.session_id === summary.session_id) setDetail(null);
      setNotice("练习记录已永久删除。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除记录失败");
    } finally {
      setBusy(false);
    }
  }

  async function restore(summary: SessionSummary) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await restoreSession(summary.session_id);
      setItems((current) => current.map((item) => (
        item.session_id === summary.session_id ? { ...item, archived: false } : item
      )));
      setNotice("记录已恢复到正常列表。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复记录失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelected(sessionId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(sessionId)) next.delete(sessionId);
      else next.add(sessionId);
      return next;
    });
  }

  function toggleAllVisible() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        selectableFiltered.forEach((item) => next.delete(item.session_id));
      } else {
        selectableFiltered.forEach((item) => next.add(item.session_id));
      }
      return next;
    });
  }

  async function removeSelected() {
    const sessionIds = [...selectedIds];
    if (!sessionIds.length) return;
    if (!window.confirm(`确定永久删除已选择的 ${sessionIds.length} 条记录吗？删除后无法恢复。`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await deleteSessions(sessionIds);
      const deletedIds = new Set(result.deleted_ids);
      setItems((current) => current.filter((item) => !deletedIds.has(item.session_id)));
      setSelectedIds(new Set());
      if (detail && deletedIds.has(detail.summary.session_id)) setDetail(null);
      setNotice(`已永久删除 ${result.deleted_count} 条练习记录。`);
      if (result.missing_ids.length) {
        setError(`${result.missing_ids.length} 条记录未找到，其他记录已正常处理。`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "批量删除失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-wrap history-page">
      <header className="page-heading">
        <p className="eyebrow">PRACTICE HISTORY</p>
        <h1>练习记录中心</h1>
        <p>集中查看完整模考、Part、题型和错题再练记录。删除操作会永久清除记录，无法恢复。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      {notice ? <div className="history-notice">{notice}</div> : null}
      <div className="history-toolbar">
        <input aria-label="搜索套题" placeholder="搜索套题名称" value={query} onChange={(event) => { setQuery(event.target.value); setSelectedIds(new Set()); }} />
        <select aria-label="按训练模式筛选" value={mode} onChange={(event) => { setMode(event.target.value); setSelectedIds(new Set()); }}>
          <option value="all">全部模式（{items.length}）</option>
          {modes.map((value) => <option value={value} key={value}>{value}（{items.filter((item) => item.exam_mode === value).length}）</option>)}
        </select>
        <select aria-label="按记录状态筛选" value={recordStatus} onChange={(event) => { setRecordStatus(event.target.value as typeof recordStatus); setSelectedIds(new Set()); }}>
          <option value="active">正常记录</option><option value="archived">已归档</option><option value="all">全部状态</option>
        </select>
      </div>
      <div className="history-batch-bar">
        <span>已选择 <strong>{selectedIds.size}</strong> 条</span>
        <button className="secondary-button" type="button" disabled={busy || !selectableFiltered.length} onClick={toggleAllVisible}>
          {allVisibleSelected ? "取消全选" : "全选当前"}
        </button>
        <button className="history-delete-button" type="button" disabled={busy || !selectedIds.size} onClick={() => void removeSelected()}>
          {busy ? "处理中…" : `批量删除（${selectedIds.size}）`}
        </button>
        <small>请谨慎操作：删除后无法恢复。</small>
      </div>
      {loading ? <div className="review-empty">正在读取记录…</div> : filtered.length ? (
        <div className="history-table-wrap">
          <table className="history-table">
            <thead><tr>
              <th className="history-select-column">
                <input
                  type="checkbox"
                  aria-label="选择全部当前记录"
                  checked={allVisibleSelected}
                  disabled={!selectableFiltered.length}
                  onChange={toggleAllVisible}
                />
              </th>
              <th>时间</th><th>练习</th><th>模式</th><th>成绩</th><th>Band</th><th>操作</th>
            </tr></thead>
            <tbody>{filtered.map((item) => (
              <tr key={item.session_id}>
                <td className="history-select-column">
                  <input
                    type="checkbox"
                    aria-label={`选择 ${item.test_title} ${dateText(item.created_at)}`}
                    checked={selectedIds.has(item.session_id)}
                    onChange={() => toggleSelected(item.session_id)}
                  />
                </td>
                <td>{dateText(item.created_at)}</td><td><strong>{item.test_title}</strong><small>{item.test_id}</small></td>
                <td>{item.exam_mode}</td><td>{item.score}/{item.total} · {item.accuracy}%</td>
                <td>{item.estimated_band == null ? "不适用" : item.estimated_band.toFixed(1)}</td>
                <td><div className="history-row-actions">
                  <button className="primary-button" type="button" onClick={() => openDetailedReport(item)}>详细报告</button>
                  <button className="secondary-button" type="button" onClick={() => void open(item)}>概览 / 导出</button>
                  {item.archived
                    ? <button className="secondary-button" type="button" disabled={busy} onClick={() => void restore(item)}>恢复</button>
                    : null}
                  <button className="history-delete-button compact" type="button" disabled={busy} onClick={() => void remove(item)}>永久删除</button>
                </div></td>
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
              <button className="history-delete-button" type="button" disabled={busy} onClick={() => void remove(detail.summary)}>永久删除此记录</button>
              <button className="secondary-button" type="button" onClick={() => openDetailedReport(detail.summary)}>打开原文与错题对比</button>
              <a className="primary-button" href={sessionReportDownloadUrl(detail.summary.session_id, "pdf")}>下载正式 PDF</a>
              <a className="secondary-button" href={sessionReportDownloadUrl(detail.summary.session_id, "docx")}>下载 DOCX</a>
              <button className="primary-button" type="button" onClick={() => downloadJson(detail.summary, detail.result)}>导出 JSON</button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
