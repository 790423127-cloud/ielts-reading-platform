"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import AiTeacherPanel from "@/components/AiTeacherPanel";
import {
  fetchLearningPlan,
  type LearningPlan,
  type LearningTask
} from "@/lib/learningApi";

const STATUS_CLASS: Record<string, string> = {
  not_started: "neutral",
  learning: "learning",
  pending_validation: "validation",
  pending_review: "review",
  mastered: "mastered",
  retrain: "retrain"
};

function formatDate(value?: string | null): string {
  if (!value) return "—";
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

function taskMessage(task: LearningTask): string {
  if (task.status === "not_started") return `先完成至少 ${task.minimum_questions} 道该能力真实题。`;
  if (task.status === "learning") return `本次完成 ${task.current_question_count}/${task.minimum_questions} 题，继续补足有效题量。`;
  if (task.status === "pending_validation") return `已在一个日期达标，还需另一个日期连续达到 ${task.target_accuracy}% 。`;
  if (task.status === "pending_review") return `跨日期训练已达标，等待 ${formatDate(task.next_review_at)} 后复习验证。`;
  if (task.status === "mastered") return "跨日期训练和后续复习均已通过。";
  return `最近训练未达目标，需要重新完成 ${task.minimum_questions} 题并达到 ${task.target_accuracy}% 。`;
}

export default function LearningPlanCenter() {
  const [plan, setPlan] = useState<LearningPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchLearningPlan("owner", controller.signal)
      .then(setPlan)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "学习计划读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const mastery = useMemo(
    () => [...(plan?.skill_mastery || [])].sort((a, b) => a.weighted_accuracy - b.weighted_accuracy),
    [plan]
  );

  return (
    <div className="page-wrap learning-plan-page">
      <header className="page-heading">
        <p className="eyebrow">BACKEND LEARNING PLAN</p>
        <h1>学习计划与掌握度</h1>
        <p>任务由真实做题记录自动生成。至少8题、连续两个不同日期达标，并在第3天后完成一次合格复习，才会标记掌握。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}

      <section className="plan-policy-banner">
        <div><span>有效训练</span><strong>至少8题</strong></div>
        <div><span>连续达标</span><strong>2个不同日期</strong></div>
        <div><span>后续复习</span><strong>第3天后</strong></div>
        <div><span>手动/AI完成</span><strong>不允许</strong></div>
      </section>

      {loading ? <div className="plan-loading">正在根据Session同步学习计划…</div> : plan ? (
        <>
          <section className="plan-stat-strip">
            <article><span>进行中任务</span><strong>{plan.active_task_count}</strong></article>
            <article><span>到期复习</span><strong>{plan.due_review_count}</strong></article>
            <article><span>已掌握能力</span><strong>{plan.mastered_skill_count}</strong></article>
            <article><span>系统任务总数</span><strong>{plan.tasks.length}</strong></article>
          </section>

          {plan.tasks.length ? (
            <section className="plan-task-section">
              <div className="section-title-row">
                <div><span>PRIORITY TASKS</span><h2>系统安排的训练任务</h2></div>
                <small>刷新页面会重新读取Session，但不会重复创建任务。</small>
              </div>
              <div className="plan-task-list">
                {plan.tasks.map((task) => {
                  const questionProgress = Math.min(100, task.minimum_questions ? task.current_question_count / task.minimum_questions * 100 : 0);
                  const accuracyProgress = Math.min(100, task.target_accuracy ? task.recent_accuracy / task.target_accuracy * 100 : 0);
                  return (
                    <article className={`plan-task-card ${STATUS_CLASS[task.status] || "neutral"}`} key={task.id}>
                      <div className="task-status-column">
                        <span>{task.status_label}</span>
                        <strong>{task.skill_label}</strong>
                        <small>累计错误 {task.wrong_count} 次</small>
                      </div>
                      <div className="task-main-column">
                        <div className="task-heading-row">
                          <div>
                            <h3>{task.skill_label}训练</h3>
                            <p>{taskMessage(task)}</p>
                          </div>
                          <div className="task-target-chip">目标 {task.target_accuracy}%</div>
                        </div>
                        <div className="task-progress-grid">
                          <div>
                            <span>本次有效题量 <b>{task.current_question_count}/{task.minimum_questions}</b></span>
                            <div className="plan-progress"><i style={{ width: `${questionProgress}%` }} /></div>
                          </div>
                          <div>
                            <span>最近正确率 <b>{task.recent_accuracy}%/{task.target_accuracy}%</b></span>
                            <div className="plan-progress"><i style={{ width: `${accuracyProgress}%` }} /></div>
                          </div>
                          <div>
                            <span>不同日期连续达标 <b>{task.success_streak}/{task.required_success_days}</b></span>
                            <div className="plan-day-dots">
                              {Array.from({ length: task.required_success_days }).map((_, index) => <i key={index} className={index < task.success_streak ? "done" : ""} />)}
                            </div>
                          </div>
                        </div>
                        <div className="task-metadata">
                          <span>最近错误：{formatDate(task.source_wrong_at)}</span>
                          <span>复习时间：{formatDate(task.next_review_at)}</span>
                          <span>错误原因：{task.reason_code || "待训练验证"}</span>
                        </div>
                      </div>
                      <div className="task-actions">
                        {task.recommended_course_id ? <Link className="secondary-button" href={`/methods?course=${encodeURIComponent(task.recommended_course_id)}`}>学习对应方法</Link> : null}
                        <Link className="primary-button" href={`/ability?skill=${encodeURIComponent(task.skill_key)}`}>{task.status === "pending_review" ? "开始复习验证" : "开始真实题训练"}</Link>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          ) : (
            <section className="plan-empty">
              <strong>还没有可生成的学习任务</strong>
              <p>先完成一次题库练习或能力训练。系统会根据真实错误自动建立任务，不需要手工添加。</p>
              <Link className="primary-button" href="/practice">进入题库与考试</Link>
            </section>
          )}

          <section className="mastery-section">
            <div className="section-title-row">
              <div><span>SKILL MASTERY</span><h2>能力掌握档案</h2></div>
              <small>只由练习结果更新，课程阅读和AI对话不能修改。</small>
            </div>
            {mastery.length ? (
              <div className="mastery-table-wrap">
                <table className="mastery-table">
                  <thead><tr><th>能力</th><th>累计题量</th><th>加权正确率</th><th>最近正确率</th><th>跨日连续达标</th><th>复习</th><th>状态</th></tr></thead>
                  <tbody>{mastery.map((row) => (
                    <tr key={row.skill_key}>
                      <td><strong>{row.skill_label}</strong></td>
                      <td>{row.correct}/{row.attempts}</td>
                      <td>{row.weighted_accuracy}%</td>
                      <td>{row.recent_accuracy}%</td>
                      <td>{row.target_hit_streak}/2</td>
                      <td>{row.review_successes ? "通过" : formatDate(row.next_review_at)}</td>
                      <td><span className={`mastery-status ${STATUS_CLASS[row.status] || "neutral"}`}>{row.status_label}</span></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            ) : <div className="mastery-empty">完成训练后，这里会形成七种能力的长期档案。</div>}
          </section>

          <section className="plan-integrity-note">
            <strong>掌握度保护</strong>
            <p>系统没有“手动完成”接口，AI老师也没有权限修改任务状态、题目答案、成绩或掌握度。</p>
          </section>

          <AiTeacherPanel
            contextType="plan"
            title="问今天的学习安排"
            description="AI读取当前服务端学习计划进行解释，但任务顺序、状态和掌握度仍只由真实做题记录决定。"
            suggestions={["我今天应该先练什么？", "我最薄弱的能力是什么？", "为什么这个任务还没有掌握？"]}
          />
        </>
      ) : null}
    </div>
  );
}
