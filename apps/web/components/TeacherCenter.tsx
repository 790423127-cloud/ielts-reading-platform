"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createTeacherAssignment,
  createTeacherReportSnapshot,
  fetchSessions,
  fetchTeacherAssignments,
  fetchTeacherReport,
  fetchTeacherReportSnapshots,
  teacherReportDownloadUrl,
  updateTeacherAssignment,
  type SessionSummary,
  type StageReport,
  type TeacherAssignment,
  type TeacherAssignmentModule,
  type TeacherReportSnapshot
} from "@/lib/api";

export default function TeacherCenter() {
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [snapshots, setSnapshots] = useState<TeacherReportSnapshot[]>([]);
  const [active, setActive] = useState<TeacherAssignment | null>(null);
  const [activeModuleId, setActiveModuleId] = useState("");
  const [report, setReport] = useState<StageReport | null>(null);
  const [reportSource, setReportSource] = useState<{ assignmentId: string } | { snapshotId: string } | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [assignmentRows, sessionRows, snapshotRows] = await Promise.all([
        fetchTeacherAssignments(), fetchSessions(), fetchTeacherReportSnapshots()
      ]);
      setAssignments(assignmentRows);
      setSessions(sessionRows);
      setSnapshots(snapshotRows);
      setActive((current) => current
        ? assignmentRows.find((row) => row.id === current.id) || null
        : null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "教师中心读取失败");
    }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const activeModule = useMemo(
    () => active?.modules.find((module) => module.id === activeModuleId) || active?.modules[0] || null,
    [active, activeModuleId]
  );
  const linked = useMemo(() => new Set(activeModule?.session_ids || []), [activeModule]);

  useEffect(() => {
    if (active && !active.modules.some((module) => module.id === activeModuleId)) {
      setActiveModuleId(active.modules[0]?.id || "");
    }
  }, [active, activeModuleId]);

  async function create() {
    if (!title.trim()) return;
    try {
      const row = await createTeacherAssignment({ title: title.trim(), description: description.trim() });
      setTitle(""); setDescription(""); setActive(row); setActiveModuleId(row.modules[0]?.id || ""); await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建作业失败");
    }
  }

  async function updateModule(module: TeacherAssignmentModule) {
    if (!active) return;
    await save({
      ...active,
      modules: active.modules.map((row) => row.id === module.id ? module : row)
    });
  }

  async function addModule() {
    if (!active) return;
    const newModule: TeacherAssignmentModule = {
      id: `module-${Date.now().toString(36)}`,
      title: `练习模块 ${active.modules.length + 1}`,
      module_type: "mixed",
      target_count: 0,
      sort_order: active.modules.length,
      session_ids: []
    };
    setActiveModuleId(newModule.id);
    await save({ ...active, modules: [...active.modules, newModule] });
  }

  async function removeModule(moduleId: string) {
    if (!active || active.modules.length <= 1) return;
    const modules = active.modules.filter((module) => module.id !== moduleId);
    setActiveModuleId(modules[0]?.id || "");
    await save({ ...active, modules });
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
      setReportSource({ assignmentId: assignment.id });
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
        当前是本人本机单用户工作流，全部作业和报告只归本地 owner；本阶段不建设多人账号或公开发布能力。
      </p>
      {error ? <div className="page-error">{error}</div> : null}
      <div className="teacher-layout">
        <aside className="teacher-assignment-list">
          <h2>作业中心</h2>
          <label><span>新作业标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
          <label><span>说明</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} /></label>
          <button className="primary-button" type="button" disabled={!title.trim()} onClick={() => void create()}>创建作业</button>
          <div>{assignments.map((item) => (
            <button type="button" className={active?.id === item.id ? "teacher-assignment-card active" : "teacher-assignment-card"} key={item.id} onClick={() => { setActive(item); setActiveModuleId(item.modules[0]?.id || ""); setReport(null); setReportSource(null); }}>
              <strong>{item.title}</strong><span>{item.status} · {item.modules.length} 个模块 · {item.session_ids.length} 条记录</span>
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
              <section className="teacher-module-editor">
                <div className="teacher-module-heading">
                  <div><span>ASSIGNMENT MODULES</span><h3>作业模块</h3><p>可以把整套题、单 Part、题型专项和错题复习分别组织，再关联对应练习记录。</p></div>
                  <button className="secondary-button" type="button" onClick={() => void addModule()}>新增模块</button>
                </div>
                <div className="teacher-module-tabs">
                  {active.modules.map((module, index) => (
                    <button
                      type="button"
                      className={activeModule?.id === module.id ? "active" : ""}
                      key={module.id}
                      onClick={() => setActiveModuleId(module.id)}
                    >
                      <b>{index + 1}</b><span>{module.title}</span><small>{module.session_ids.length} 条记录</small>
                    </button>
                  ))}
                </div>
                {activeModule ? (
                  <div className="teacher-module-fields">
                    <label>
                      <span>模块名称</span>
                      <input
                        key={`title-${activeModule.id}-${activeModule.title}`}
                        defaultValue={activeModule.title}
                        onBlur={(event) => void updateModule({
                          ...activeModule,
                          title: event.target.value.trim() || "未命名模块"
                        })}
                      />
                    </label>
                    <label>
                      <span>训练类型</span>
                      <select value={activeModule.module_type} onChange={(event) => {
                        void updateModule({ ...activeModule, module_type: event.target.value as TeacherAssignmentModule["module_type"] });
                      }}>
                        <option value="full_test">完整套题</option>
                        <option value="part">单 Part</option>
                        <option value="question_type">题型专项</option>
                        <option value="review">错题复习</option>
                        <option value="mixed">混合训练</option>
                      </select>
                    </label>
                    <label>
                      <span>目标记录数</span>
                      <input
                        key={`target-${activeModule.id}-${activeModule.target_count}`}
                        type="number"
                        min={0}
                        max={500}
                        defaultValue={activeModule.target_count}
                        onBlur={(event) => void updateModule({
                          ...activeModule,
                          target_count: Math.max(0, Number(event.target.value) || 0)
                        })}
                      />
                    </label>
                    <button className="teacher-module-remove" type="button" disabled={active.modules.length <= 1} onClick={() => void removeModule(activeModule.id)}>删除此模块</button>
                  </div>
                ) : null}
              </section>
              <h3>为当前模块关联练习记录</h3>
              <div className="teacher-session-picker">{sessions.map((session) => (
                <label key={session.session_id} className={linked.has(session.session_id) ? "selected" : ""}>
                  <input type="checkbox" checked={linked.has(session.session_id)} onChange={() => {
                    if (!activeModule) return;
                    const nextIds = linked.has(session.session_id)
                      ? activeModule.session_ids.filter((id) => id !== session.session_id)
                      : [...activeModule.session_ids, session.session_id];
                    void updateModule({ ...activeModule, session_ids: nextIds });
                  }} />
                  <span><strong>{session.test_title}</strong><small>{session.score}/{session.total} · {session.accuracy}%</small></span>
                </label>
              ))}</div>
              <div className="teacher-actions">
                <button className="secondary-button" type="button" onClick={() => void openReport(active)}>生成当前报告</button>
                <button className="primary-button" type="button" disabled={!active.session_ids.length} onClick={async () => { await createTeacherReportSnapshot(active.id); await refresh(); }}>冻结报告快照</button>
              </div>
              {report ? <TeacherReportView report={report} source={reportSource} /> : null}
            </>
          ) : <div className="review-empty">创建或选择一项作业后，可关联练习记录。</div>}
        </main>
      </div>
      <section className="teacher-snapshots">
        <div><p className="eyebrow">REPORT HISTORY</p><h2>教师报告历史</h2></div>
        {snapshots.length ? snapshots.map((snapshot) => (
          <button key={snapshot.id} type="button" onClick={() => { setReport(snapshot.report); setReportSource({ snapshotId: snapshot.id }); }}>
            <strong>{snapshot.title}</strong><span>{new Date(snapshot.created_at).toLocaleString("zh-CN")} · {snapshot.report.summary.session_count} 次练习</span>
          </button>
        )) : <p>还没有冻结的报告快照。</p>}
      </section>
    </section>
  );
}

function TeacherReportView({
  report,
  source
}: {
  report: StageReport;
  source: { assignmentId: string } | { snapshotId: string } | null;
}) {
  return (
    <section className="teacher-report-preview">
      <header>
        <h3>教师报告预览</h3>
        <div className="teacher-report-downloads">
          {source ? <a className="secondary-button" href={teacherReportDownloadUrl(source, "pdf")}>下载正式 PDF</a> : null}
          {source ? <a className="secondary-button" href={teacherReportDownloadUrl(source, "docx")}>下载 DOCX</a> : null}
          <button type="button" className="secondary-button" onClick={() => window.print()}>打印</button>
        </div>
      </header>
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
