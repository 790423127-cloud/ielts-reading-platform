"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchMethodCourse, fetchMethodCourses, type MethodCourse } from "@/lib/api";

type CourseTab = "foundation" | "subtype";

export default function MethodLearningCenter() {
  const [courses, setCourses] = useState<MethodCourse[]>([]);
  const [tab, setTab] = useState<CourseTab>("foundation");
  const [activeId, setActiveId] = useState("");
  const [activeDetail, setActiveDetail] = useState<MethodCourse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchMethodCourses(controller.signal)
      .then((items) => {
        setCourses(items);
        const queryCourse = new URLSearchParams(window.location.search).get("course") || "";
        const matched = items.find((item) => item.id === queryCourse);
        const initial = matched || items.find((item) => item.kind === "foundation") || items[0];
        if (initial) {
          setActiveId(initial.id);
          setTab(initial.kind);
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "方法课读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const visibleCourses = useMemo(
    () => courses.filter((course) => course.kind === tab),
    [courses, tab]
  );
  const activeCourse = courses.find((course) => course.id === activeId) || visibleCourses[0];
  const displayedCourse = activeDetail?.id === activeCourse?.id ? activeDetail : activeCourse;
  const displayedSteps: NonNullable<MethodCourse["standard_method"]> = displayedCourse?.standard_method
    || (displayedCourse?.steps || []).map((step) => ({ title: step, action: "" }));

  useEffect(() => {
    if (!activeCourse || activeCourse.kind !== "subtype") {
      setActiveDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    fetchMethodCourse(activeCourse.id, controller.signal)
      .then(setActiveDetail)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "详细课程读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailLoading(false);
      });
    return () => controller.abort();
  }, [activeCourse?.id, activeCourse?.kind]);

  function changeTab(nextTab: CourseTab) {
    setTab(nextTab);
    const first = courses.find((course) => course.kind === nextTab);
    if (first) setActiveId(first.id);
  }

  return (
    <div className="page-wrap methods-page">
      <header className="page-heading">
        <p className="eyebrow">FIXED METHOD COURSES</p>
        <h1>做题方法学习中心</h1>
        <p>5个基础方法和17种具体题型课程全部为固定离线内容，AI调用次数为0。阅读课程不会自动标记掌握，掌握度必须通过真实新题验证。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="method-summary-strip">
        <article><span>基础方法</span><strong>5</strong></article>
        <article><span>精确题型课</span><strong>17</strong></article>
        <article><span>课程AI调用</span><strong>0</strong></article>
        <article><span>掌握判定</span><strong>真实做题</strong></article>
      </section>

      <div className="method-tabs" role="tablist" aria-label="方法课分类">
        <button type="button" role="tab" aria-selected={tab === "foundation"} className={tab === "foundation" ? "active" : ""} onClick={() => changeTab("foundation")}>基础能力方法</button>
        <button type="button" role="tab" aria-selected={tab === "subtype"} className={tab === "subtype" ? "active" : ""} onClick={() => changeTab("subtype")}>17种题型方法</button>
      </div>

      {loading ? <div className="method-loading">正在读取固定课程…</div> : (
        <div className="method-layout">
          <aside className="method-course-list" aria-label="课程列表">
            {visibleCourses.map((course, index) => (
              <button
                type="button"
                key={course.id}
                className={course.id === activeCourse?.id ? "active" : ""}
                onClick={() => setActiveId(course.id)}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{course.title}</strong><small>{course.kind === "foundation" ? "基础方法" : `${course.family_label || "题型方法"} · ${course.section_count || 12} 模块`}</small></div>
              </button>
            ))}
          </aside>
          {displayedCourse ? (
            <article className="method-course-detail">
              <div className="method-detail-heading">
                <span>{displayedCourse.kind === "foundation" ? "FOUNDATION" : `${displayedCourse.family_label || "QUESTION TYPE"} · ${displayedCourse.section_count || 12} 个教学模块`}</span>
                <h2>{displayedCourse.title}</h2>
                <p>{displayedCourse.objective}</p>
                {displayedCourse.kind === "subtype" && (
                  <div className="method-detail-meta">
                    <b>建议 {displayedCourse.suggested_minutes || 25} 分钟</b>
                    <b>固定离线内容</b>
                    <b>AI 调用 0</b>
                  </div>
                )}
              </div>

              {detailLoading && displayedCourse.kind === "subtype" ? <div className="method-loading">正在读取完整旧版课程内容…</div> : null}

              {displayedCourse.child_guide && (
                <section className="method-child-guide">
                  <p className="eyebrow">先用最简单的话理解</p>
                  <h3>{displayedCourse.child_guide.memory_sentence}</h3>
                  <p>{displayedCourse.child_guide.plain_language}</p>
                  <strong>本课目标：{displayedCourse.child_guide.goal}</strong>
                </section>
              )}

              {displayedCourse.recognition && displayedCourse.opening && (
                <section className="method-rich-section">
                  <div className="method-section-title"><span>01</span><div><h3>识别题型与开场动作</h3><p>拿到题目后先确认它是什么，再开始定位。</p></div></div>
                  <div className="method-recognition-grid">
                    <div><h4>看到这些特征</h4><ul>{displayedCourse.recognition.map((item) => <li key={item}>{item}</li>)}</ul></div>
                    <div className="method-opening-grid">
                      <p><b>先看</b>{displayedCourse.opening.look}</p>
                      <p><b>再标</b>{displayedCourse.opening.mark}</p>
                      <p><b>心里说</b>{displayedCourse.opening.say}</p>
                      <p><b>不要做</b>{displayedCourse.opening.avoid}</p>
                    </div>
                  </div>
                </section>
              )}

              <section className="method-rich-section">
                <div className="method-section-title"><span>{displayedCourse.standard_method ? "02" : "01"}</span><div><h3>标准做题步骤</h3><p>按照顺序执行，不靠感觉跳步。</p></div></div>
                <ol className={displayedCourse.standard_method ? "method-step-list rich" : "method-step-list"}>
                  {displayedSteps.map((step, index) => (
                    <li key={`${step.title}-${index}`}>
                      <span>{index + 1}</span>
                      <div><h4>{step.title}</h4>{step.action && <p>{step.action}</p>}{step.why && <small><b>为什么：</b>{step.why}</small>}{step.example && <em>例：{step.example}</em>}</div>
                    </li>
                  ))}
                </ol>
              </section>

              {displayedCourse.mini_example && (
                <section className="method-rich-section method-example">
                  <div className="method-section-title"><span>03</span><div><h3>微型例题：完整走一遍</h3><p>重点是推理过程，不是背答案。</p></div></div>
                  <blockquote>{displayedCourse.mini_example.context}</blockquote>
                  <p><strong>{displayedCourse.mini_example.question}</strong></p>
                  <p className="method-example-answer">答案：{displayedCourse.mini_example.answer}</p>
                  <ol>{displayedCourse.mini_example.reasoning.map((item) => <li key={item}>{item}</li>)}</ol>
                </section>
              )}

              {displayedCourse.decision_guide && (
                <section className="method-rich-section">
                  <div className="method-section-title"><span>04</span><div><h3>判断与决策表</h3><p>把常见信号直接转换为下一步动作。</p></div></div>
                  <div className="method-table-wrap"><table className="method-decision-table"><thead><tr><th>看到什么</th><th>说明什么</th><th>怎么做</th><th>例子</th></tr></thead><tbody>
                    {displayedCourse.decision_guide.map((row) => <tr key={row.signal}><td>{row.signal}</td><td>{row.meaning}</td><td><strong>{row.action}</strong></td><td>{row.example || "—"}</td></tr>)}
                  </tbody></table></div>
                </section>
              )}

              {displayedCourse.difficulty_ladder && (
                <section className="method-rich-section">
                  <div className="method-section-title"><span>05</span><div><h3>简单题到困难题</h3><p>难度变化时，方法也要跟着升级。</p></div></div>
                  <div className="method-difficulty-grid">
                    {displayedCourse.difficulty_ladder.map((level) => <article key={level.level}><strong>{level.level}</strong><p>{level.signal}</p><b>{level.action}</b>{level.course_tip && <small>{level.course_tip}</small>}</article>)}
                  </div>
                </section>
              )}

              {displayedCourse.vocabulary_guide && (
                <details className="method-expand-section" open>
                  <summary>06 · 生词处理流程（{displayedCourse.vocabulary_guide.steps.length} 步）</summary>
                  <p className="method-fallback">{displayedCourse.vocabulary_guide.fallback}</p>
                  <ol className="method-compact-steps">{displayedCourse.vocabulary_guide.steps.map((step, index) => <li key={step.title}><span>{index + 1}</span><div><strong>{step.title}</strong><p>{step.action}</p>{step.example && <small>例：{step.example}</small>}</div></li>)}</ol>
                </details>
              )}

              {displayedCourse.long_sentence_guide && (
                <details className="method-expand-section">
                  <summary>07 · 长难句拆解（{displayedCourse.long_sentence_guide.length} 步）</summary>
                  <ol className="method-compact-steps">{displayedCourse.long_sentence_guide.map((step, index) => <li key={step.title}><span>{index + 1}</span><div><strong>{step.title}</strong><p>{step.action}</p>{step.example && <small>例：{step.example}</small>}</div></li>)}</ol>
                </details>
              )}

              {displayedCourse.hard_rescue && displayedCourse.time_plan && (
                <div className="method-detail-grid">
                  <section className="method-traps">
                    <h3>困难题救援步骤</h3>
                    <ol>{displayedCourse.hard_rescue.map((item) => <li key={item}>{item}</li>)}</ol>
                  </section>
                  <section className="method-time-plan">
                    <h3>考场时间方案</h3>
                    <p><span>简单题</span><strong>{displayedCourse.time_plan.easy}</strong></p>
                    <p><span>普通题</span><strong>{displayedCourse.time_plan.normal}</strong></p>
                    <p><span>困难题</span><strong>{displayedCourse.time_plan.hard}</strong></p>
                  </section>
                </div>
              )}

              <div className="method-detail-grid">
                <section className="method-traps">
                  <h3>常见干扰</h3>
                  <ul>{(displayedCourse.traps || []).map((trap) => <li key={trap}>{trap}</li>)}</ul>
                </section>
                <section className="method-checklist">
                  <h3>下次检查清单</h3>
                  <ul>{(displayedCourse.checklist || []).map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
              </div>
              <div className="method-validation-note">
                <div><span>课程完成规则</span><strong>看完不等于掌握</strong><p>回到真实题训练，达到系统规定的题量和连续正确标准后，才会进入掌握状态。</p></div>
                <div className="method-actions">
                  {displayedCourse.subtype ? <Link className="secondary-button" href="/review">查看相关错题</Link> : null}
                  <Link className="primary-button" href="/ability">进入能力训练</Link>
                </div>
              </div>
            </article>
          ) : null}
        </div>
      )}
    </div>
  );
}
