"use client";

import { useEffect, useMemo, useState } from "react";

import {
  createTeacherAssignment,
  createTeacherReportSnapshot,
  fetchSessions,
  fetchTeacherAssignments,
  fetchTeacherReport,
  fetchTeacherReportSnapshots,
  updateTeacherAssignment,
  type SessionSummary,
  type StageReport,
  type TeacherAssignment,
  type TeacherReportSnapshot
} from "@/lib/api";

export default function TeacherCenter() {
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [snapshots, setSnapshots] = useState<TeacherReportSnapshot[]>([]);
  const [active, setActive] = useState<TeacherAssignment | null>(null);
  const [report, setReport] = useState<StageReport | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const refresh = async () => {
    try {
      const [assignmentRows, sessionRows, snapshotRows] = await Promise.all([
        fetchTeacherAssignments(), fetchSessions(), fetchTeacherReportSnapshots()
      ]);
      setAssignments(assignmentRows);
      setSessions(sessionRows);
      setSnapshots(snapshotRows);
      if (active) setActive(assignmentRows.find((row) => row.id === active.id) || null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "教师中心读取失败");
    }
  };
  useEffect(() => { void refresh(); }, []);

  const linked = useMemo(() => new Set(active?.session_ids || []), [active]);

  async function create() {
    if (!title.trim()) return;
    try {
      const row = await createTeacherAssignment({ title: title.trim(), description: description.trim() });
      setTitle(""); setDescription(""); setActive(row); await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建作业失败");
    }
  }

  async function save(next: TeacherAssignment) {
    try {
      const row = await updateTeacherAssignment(next);
      setActive(row);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存作业失败");
    }
  }

  async function openReport(assignment: TeacherAssignment) {
    try {
      setActive(assignment);
      setReport(await fetchTeacherReport(assignment.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "报告生成失败");
    }
  }

  return (
    <section className="page-wrap teacher-page">
      <header className="page-heading">
        <p className="eyebrow">TEACHER ASSIGNMENTS</p>
        <h1>真人老师作业与报告</h1>
        <p>把已完成的练习记录编入作业，并生成可冻结历史版本的确定性教师报告。此处不调用 AI，也不冒充老师结论。</p>
      </header>
      <p className="teacher-scope-notice">
        当前是本机单用户工作流；老师/学生账号、跨账号发布和权限隔离尚未接入，不能当作正式线上作业系统使用。
      </p>
      {error ? <div className="page-error">{error}</div> : null}
      <div className="teacher-layout">
        <aside className="teacher-assignment-list">
          <h2>作业中心</h2>
          <label><span>新作业标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label><span>说明</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <button className="primary-button" type="button" disabled={!title.trim()} onClick={() => void create()}>创建作业</button>
          <div>{assignments.map((item) => (
            <button type="button" className={active?.id === item.id ? "teacher-assignment-card active" : "teacher-assignment-card"} key={item.id} onClick={() => { setActive(item); setReport(null); }}>
              <strong>{item.title}</strong><span>{item.status} · {item.session_ids.length} 条记录</span>
            </button>
          ))}</div>
        </aside>
        <main className="teacher-detail">
          {active ? (
            <>
              <header><div><span>ASSIGNMENT DETAIL</span><h2>{active.title}</h2><p>{active.description || "暂无作业说明"}</p></div>
                <select value={active.status} onChange={(event) => void save({ ...active, status: event.target.value as TeacherAssignment["status"] })}>
                  <option value="active">进行中</option><option value="completed">已完成</option><option value="archived">已归档</option>
                </select>
              </header>
              <h3>关联练习记录</h3>
              <div className="teacher-session-picker">{sessions.map((session) => (
                <label key={session.session_id} className={linked.has(session.session_id) ? "selected" : ""}>
                  <input type="checkbox" checked={linked.has(session.session_id)} onChange={() => {
                    const nextIds = linked.has(session.session_id)
                      ? active.session_ids.filter((id) => id !== session.session_id)
                      : [...active.session_ids, session.session_id];
                    void save({ ...active, session_ids: nextIds });
                  }} />
                  <span><strong>{session.test_title}</strong><small>{session.score}/{session.total} · {session.accuracy}%</small></span>
                </label>
              ))}</div>
              <div className="teacher-actions">
                <button className="secondary-button" type="button" onClick={() => void openReport(active)}>生成当前报告</button>
                <button className="primary-button" type="button" disabled={!active.session_ids.length} onClick={async () => { await createTeacherReportSnapshot(active.id); await refresh(); }}>冻结报告快照</button>
              </div>
              {report ? <TeacherReportView report={report} /> : null}
            </>
          ) : <div className="review-empty">创建或选择一项作业后，可关联练习记录。</div>}
        </main>
      </div>
      <section className="teacher-snapshots">
        <div><p className="eyebrow">REPORT HISTORY</p><h2>教师报告历史</h2></div>
        {snapshots.length ? snapshots.map((snapshot) => (
          <button key={snapshot.id} type="button" onClick={() => setReport(snapshot.report)}>
            <strong>{snapshot.title}</strong><span>{new Date(snapshot.created_at).toLocaleString("zh-CN")} · {snapshot.report.summary.session_count} 次练习</span>
          </button>
        )) : <p>还没有冻结的报告快照。</p>}
      </section>
    </section>
  );
}

function TeacherReportView({ report }: { report: StageReport }) {
  return (
    <section className="teacher-report-preview">
      <header><h3>教师报告预览</h3><button type="button" className="secondary-button" onClick={() => window.print()}>打印 / 保存 PDF</button></header>
      <div><article><span>练习次数</span><strong>{report.summary.session_count}</strong></article><article><span>累计正确率</span><strong>{report.summary.accuracy}%</strong></article><article><span>总题数</span><strong>{report.summary.total_questions}</strong></article></div>
      <div className="teacher-timing-summary">
        <article>
          <span>正确题最耗时 3 道</span>
          <strong>{(report.slowest_correct_questions || []).map((item) => `Q${item.question_number} · ${item.elapsed_seconds}秒`).join("；") || "暂无新计时数据"}</strong>
        </article>
        <article>
          <span>错误题最耗时 5 道</span>
          <strong>{(report.slowest_wrong_questions || []).map((item) => `Q${item.question_number} · ${item.elapsed_seconds}秒`).join("；") || "暂无新计时数据"}</strong>
        </article>
      </div>
      {report.deterministic_interpretation.map((text) => <p key={text}>{text}</p>)}
      <small>确定性数据汇总 · AI 调用 {report.ai_calls}</small>
    </section>
  );
}
