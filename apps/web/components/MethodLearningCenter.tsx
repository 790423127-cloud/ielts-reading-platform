"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fetchMethodCourses, type MethodCourse } from "@/lib/api";

type CourseTab = "foundation" | "subtype";

export default function MethodLearningCenter() {
  const [courses, setCourses] = useState<MethodCourse[]>([]);
  const [tab, setTab] = useState<CourseTab>("foundation");
  const [activeId, setActiveId] = useState("");
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
        <button type="button" className={tab === "foundation" ? "active" : ""} onClick={() => changeTab("foundation")}>基础能力方法</button>
        <button type="button" className={tab === "subtype" ? "active" : ""} onClick={() => changeTab("subtype")}>17种题型方法</button>
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
                <div><strong>{course.title}</strong><small>{course.kind === "foundation" ? "基础方法" : course.subtype}</small></div>
              </button>
            ))}
          </aside>
          {activeCourse ? (
            <article className="method-course-detail">
              <div className="method-detail-heading">
                <span>{activeCourse.kind === "foundation" ? "FOUNDATION" : "QUESTION TYPE"}</span>
                <h2>{activeCourse.title}</h2>
                <p>{activeCourse.objective}</p>
              </div>
              <section>
                <h3>标准做题步骤</h3>
                <ol className="method-step-list">
                  {activeCourse.steps.map((step, index) => <li key={step}><span>{index + 1}</span><p>{step}</p></li>)}
                </ol>
              </section>
              <div className="method-detail-grid">
                <section className="method-traps">
                  <h3>常见干扰</h3>
                  <ul>{activeCourse.traps.map((trap) => <li key={trap}>{trap}</li>)}</ul>
                </section>
                <section className="method-checklist">
                  <h3>下次检查清单</h3>
                  <ul>{activeCourse.checklist.map((item) => <li key={item}>{item}</li>)}</ul>
                </section>
              </div>
              <div className="method-validation-note">
                <div><span>课程完成规则</span><strong>看完不等于掌握</strong><p>回到真实题训练，达到系统规定的题量和连续正确标准后，才会进入掌握状态。</p></div>
                <div className="method-actions">
                  {activeCourse.subtype ? <Link className="secondary-button" href={`/review`}>查看相关错题</Link> : null}
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
