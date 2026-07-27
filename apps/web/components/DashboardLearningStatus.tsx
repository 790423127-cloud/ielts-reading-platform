"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { fetchSessions, fetchStageReport, type SessionSummary, type StageReport } from "@/lib/api";

type RadarAxis = { label: string; value: number };

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString("zh-CN");
}

function AbilityRadar({ axes }: { axes: RadarAxis[] }) {
  const center = 120;
  const radius = 82;
  const pointAt = (index: number, scale: number) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / axes.length;
    return `${center + Math.cos(angle) * radius * scale},${center + Math.sin(angle) * radius * scale}`;
  };
  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <svg className="dashboard-radar" viewBox="0 0 240 240" role="img" aria-label="最近练习题型能力雷达图">
      {rings.map((scale) => <polygon key={scale} points={axes.map((_, index) => pointAt(index, scale)).join(" ")} />)}
      {axes.map((axis, index) => {
        const [x, y] = pointAt(index, 1).split(",").map(Number);
        const [labelX, labelY] = pointAt(index, 1.2).split(",").map(Number);
        return (
          <g key={axis.label}>
            <line x1={center} y1={center} x2={x} y2={y} />
            <text x={labelX} y={labelY}>{axis.label}</text>
          </g>
        );
      })}
      <polygon className="radar-value" points={axes.map((axis, index) => pointAt(index, Math.max(axis.value, 4) / 100)).join(" ")} />
    </svg>
  );
}

export default function DashboardLearningStatus({ children, version, statusLabel }: { children: ReactNode; version: string; statusLabel: string }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [report, setReport] = useState<StageReport | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void Promise.allSettled([
      fetchSessions("owner", controller.signal).then(setSessions),
      fetchStageReport("owner", controller.signal).then(setReport)
    ]);
    return () => controller.abort();
  }, []);

  const average = useMemo(
    () => sessions.length ? Math.round(sessions.reduce((sum, item) => sum + item.accuracy, 0) / sessions.length) : 0,
    [sessions]
  );
  const latest = sessions[0];
  const latestTrend = report?.trend.at(-1);
  const bandTrend = useMemo(
    () => sessions
      .slice(0, 4)
      .reverse()
      .filter((session): session is SessionSummary & { estimated_band: number } => typeof session.estimated_band === "number"),
    [sessions]
  );
  const bandPoints = useMemo(
    () => bandTrend.map((session, index) => {
      const x = bandTrend.length === 1 ? 130 : 4 + index * (252 / (bandTrend.length - 1));
      const y = 50 - Math.max(0, Math.min(9, session.estimated_band)) / 9 * 42;
      return { x, y };
    }),
    [bandTrend]
  );
  const radarAxes = useMemo<RadarAxis[]>(() => {
    const groups: Array<[string, (label: string) => boolean]> = [
      ["填空", (label) => /填空|completion|answer/i.test(label)],
      ["选择", (label) => /选择|choice|multiple/i.test(label)],
      ["匹配", (label) => /匹配|matching|heading/i.test(label)],
      ["判断", (label) => /判断|true|false|yes|no/i.test(label)]
    ];
    const matrix = report?.question_type_matrix || [];
    const axes = groups.map(([label, matches]) => {
      const rows = matrix.filter((row) => matches(`${row.question_type} ${row.question_subtype}`));
      const total = rows.reduce((sum, row) => sum + row.total, 0);
      const correct = rows.reduce((sum, row) => sum + row.correct, 0);
      return { label, value: total ? Math.round(correct / total * 100) : 0 };
    });
    axes.push({ label: "综合", value: report?.summary.accuracy || 0 });
    return axes;
  }, [report]);
  const nextWeakness = useMemo(() => {
    const attempted = radarAxes.filter((axis) => axis.label !== "综合" && axis.value > 0);
    return attempted.sort((a, b) => a.value - b.value)[0];
  }, [radarAxes]);

  return (
    <>
      <section className="dashboard-hero-row">
        <section className="dashboard-hero">
          <div className="dashboard-hero-copy">
            <p className="eyebrow">IELTS GENERAL TRAINING READING</p>
            <p className="dashboard-release">V{version} · {statusLabel}</p>
            <h1>IELTS G类阅读<br />AI 教练</h1>
            <p className="dashboard-lead">模考、诊断、训练、复习和真人老师报告，形成完整阅读学习闭环。</p>
            <ul className="dashboard-points">
              <li>完整机考式做题体验</li>
              <li>服务端确定性判分</li>
              <li>真实题库错题闭环</li>
              <li>可切换 AI 老师模型</li>
            </ul>
            <div className="dashboard-actions">
              <Link className="primary-button" href="/practice">开始模拟考试</Link>
              <Link className="secondary-button" href="/plan">继续学习计划</Link>
            </div>
          </div>
          <div className="reading-illustration" aria-hidden="true">
            <span className="illustration-orbit" />
            <div className="book-page left"><i /><i /><i /><i /></div>
            <div className="book-page right"><i /><i /><i /><i /></div>
            <span className="book-spine" />
            <span className="illustration-badge">A+</span>
            <span className="illustration-note">READ</span>
          </div>
        </section>
        <aside className="dashboard-hero-aside">
          <article className="dashboard-band-card">
            <span>我的预测分数</span>
            <small>基于最近一次已保存练习</small>
            <strong>{latest?.estimated_band?.toFixed(1) || "—"} <em>Band</em></strong>
            {bandPoints.length ? (
              <svg viewBox="0 0 260 56" aria-hidden="true">
                {bandPoints.length > 1 && <polyline points={bandPoints.map((point) => `${point.x},${point.y}`).join(" ")} />}
                {bandPoints.map((point, index) => <circle key={`${point.x}-${index}`} cx={point.x} cy={point.y} r="3" />)}
              </svg>
            ) : <p className="dashboard-band-empty">完成一套 40 题练习后显示真实趋势</p>}
          </article>
          <article className="dashboard-task-card">
            <span>今日任务</span>
            <small>根据真实练习数据生成</small>
            <div><b>✓</b><p><strong>{nextWeakness ? `${nextWeakness.label}专项` : "完成首次练习"}</strong><small>{nextWeakness ? `当前正确率 ${nextWeakness.value}%` : "完成后生成个性任务"}</small></p></div>
            <progress max="100" value={nextWeakness?.value || 0} />
          </article>
        </aside>
      </section>

      <section className="dashboard-next-step">
        <div><p className="eyebrow">NEXT STEP</p><strong>{latest ? `继续提升：${nextWeakness?.label || "综合阅读"}` : "从一次完整练习开始"}</strong><span>{sessions.length ? `已保存 ${sessions.length} 次练习 · 平均正确率 ${average}%` : "完成练习后，这里会显示真实学习建议"}</span></div>
        <Link className="primary-button" href={nextWeakness ? "/ability" : "/practice"}>{nextWeakness ? "继续专项训练" : "开始练习"}</Link>
      </section>

      {children}

      <section className="dashboard-learning-data">
        <div className="dashboard-section-heading">
          <div><p className="eyebrow">LEARNING DATA</p><h2>学习数据</h2></div>
          <Link href="/history">查看全部记录 →</Link>
        </div>
        <div className="dashboard-data-grid">
          <article className="dashboard-history-card">
            <header><strong>最近练习记录</strong><small>真实已保存 Session</small></header>
            <div className="dashboard-history-table-wrap">
              <table>
                <thead><tr><th>类型</th><th>名称</th><th>成绩</th><th>预计分数</th><th>用时</th><th>日期</th></tr></thead>
                <tbody>
                  {sessions.slice(0, 5).map((session) => {
                    const trend = report?.trend.find((item) => item.session_id === session.session_id);
                    return (
                      <tr key={session.session_id}>
                        <td><span className="session-mode-badge">{session.exam_mode === "mock_exam" ? "模考" : session.exam_mode === "part_practice" ? "Part" : "学习"}</span></td>
                        <td><strong>{session.test_title}</strong></td>
                        <td>{session.score}/{session.total}</td>
                        <td>{session.estimated_band?.toFixed(1) || "—"}</td>
                        <td>{formatDuration(trend?.elapsed_seconds || 0)}</td>
                        <td>{formatDate(session.created_at)}</td>
                      </tr>
                    );
                  })}
                  {!sessions.length && <tr><td colSpan={6} className="empty-table-cell">暂无练习记录，完成一次练习后自动显示。</td></tr>}
                </tbody>
              </table>
            </div>
          </article>
          <article className="dashboard-radar-card">
            <header><strong>题型能力雷达图</strong><small>{latestTrend ? "基于已保存练习" : "等待练习数据"}</small></header>
            <AbilityRadar axes={radarAxes} />
            <p>{report?.summary.total_questions ? `累计 ${report.summary.total_questions} 题 · 综合正确率 ${report.summary.accuracy}%` : "没有数据时不虚构能力分数。"}</p>
          </article>
        </div>
      </section>
    </>
  );
}
