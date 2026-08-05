"use client";

import { useEffect, useMemo, useState } from "react";

import AiTeacherPanel from "@/components/AiTeacherPanel";
import {
  createDurableAiJob,
  fetchDurableAiJobs,
  fetchWrongQuestions,
  resumeDurableAiJob,
  type DurableAiJob,
  type WrongReviewItem
} from "@/lib/api";

export default function WrongQuestionAiTeacherCenter() {
  const [items, setItems] = useState<WrongReviewItem[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchWrongQuestions("owner", controller.signal)
      .then((questions) => {
        setItems(questions);
        const first = questions[0];
        setSelectedKey(first ? `${first.source_session_id}:${first.id}` : "");
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "错题读取失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const selected = useMemo(
    () => items.find((item) => `${item.source_session_id}:${item.id}` === selectedKey) || items[0],
    [items, selectedKey]
  );

  return (
    <section className="page-wrap ai-page-section">
      <div className="section-title-row">
        <div><span>AI WRONG-QUESTION TEACHER</span><h2>继续追问一道错题</h2></div>
        <small>答案和证据由已交卷Session提供，前端不能自行填写。</small>
      </div>
      {error ? <div className="page-error">{error}</div> : null}
      {loading ? <div className="ai-teacher-loading">正在读取可提问错题…</div> : items.length ? (
        <>
          <label className="ai-context-selector">
            <span>选择错题</span>
            <select value={selectedKey} onChange={(event) => setSelectedKey(event.target.value)}>
              {items.map((item) => {
                const key = `${item.source_session_id}:${item.id}`;
                return <option key={key} value={key}>Q{item.number} · {item.question_type || item.question_subtype} · {item.prompt.slice(0, 90)}</option>;
              })}
            </select>
          </label>
          {selected ? (
            <AiTeacherPanel
              key={`${selected.source_session_id}:${selected.id}`}
              contextType="wrong_question"
              sessionId={selected.source_session_id}
              questionId={selected.id}
              title={`问 Q${selected.number} 为什么错`}
              description="AI只使用这次已交卷记录中的题干、你的答案、服务端标准答案、解析和核验证据。"
              suggestions={["我为什么会选错？", "题干和原文如何同义替换？", "正确答案的边界为什么是这样？"]}
            />
          ) : null}
        </>
      ) : <div className="ai-teacher-empty">目前没有待复习错题。完成练习后，做错的题会自动出现在这里。</div>}
      <DurableAiJobCenter items={items} />
    </section>
  );
}

function DurableAiJobCenter({ items }: { items: WrongReviewItem[] }) {
  const [jobs, setJobs] = useState<DurableAiJob[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const sessions = useMemo(() => {
    const grouped = new Map<string, { title: string; items: WrongReviewItem[] }>();
    for (const item of items) {
      const current = grouped.get(item.source_session_id) || {
        title: `${item.source_test_id} · Part ${item.source_part_number}`,
        items: []
      };
      current.items.push(item);
      grouped.set(item.source_session_id, current);
    }
    return [...grouped.entries()].map(([id, value]) => ({ id, ...value }));
  }, [items]);

  async function refresh() {
    try {
      setJobs(await fetchDurableAiJobs());
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "逐题任务读取失败");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);
  useEffect(() => {
    if (!sessions.some((row) => row.id === sessionId)) {
      setSessionId(sessions[0]?.id || "");
    }
  }, [sessions, sessionId]);

  async function create() {
    const selected = sessions.find((row) => row.id === sessionId);
    if (!selected) return;
    setBusy("create");
    setStatus("");
    try {
      const job = await createDurableAiJob({
        session_id: selected.id,
        question_ids: selected.items.map((item) => item.id),
        idempotency_key: `session:${selected.id}:all-wrong-v1`
      });
      setJobs((current) => [job, ...current.filter((row) => row.id !== job.id)]);
      setStatus("任务队列已保存；尚未调用 AI。");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "任务创建失败");
    } finally {
      setBusy("");
    }
  }

  async function resume(job: DurableAiJob) {
    if (!window.confirm("每次只处理 1 道题，可能调用当前已配置的付费 AI。是否继续？")) return;
    setBusy(job.id);
    setStatus("");
    try {
      const updated = await resumeDurableAiJob(job.id);
      setJobs((current) => current.map((row) => row.id === updated.id ? updated : row));
      setStatus(updated.status === "completed" ? "这个任务已经全部完成。" : "已处理 1 道题，剩余任务仍可继续。");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "任务处理失败，队列已保留");
      await refresh();
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="durable-ai-center">
      <div className="durable-ai-heading">
        <div>
          <span>DURABLE PER-QUESTION JOBS</span>
          <h3>可恢复的 AI 逐题讲解任务</h3>
          <p>创建只保存队列，不调用 AI；点击“继续处理”时每次最多处理 1 题，中断后可恢复，失败不会切换到其他付费模型。</p>
        </div>
        <div className="durable-ai-create">
          <select
            aria-label="选择要创建AI讲解任务的错题记录"
            value={sessionId}
            disabled={!sessions.length}
            onChange={(event) => setSessionId(event.target.value)}
          >
            {sessions.map((row) => <option key={row.id} value={row.id}>{row.title} · {row.items.length} 道错题</option>)}
          </select>
          <button className="secondary-button" type="button" disabled={!sessionId || busy === "create"} onClick={() => void create()}>
            {busy === "create" ? "创建中…" : "创建任务（0 次 AI 调用）"}
          </button>
        </div>
      </div>
      {status ? <p className="durable-ai-status">{status}</p> : null}
      <div className="durable-ai-jobs">
        {jobs.map((job) => (
          <article key={job.id}>
            <header>
              <div>
                <strong>{job.completed_items}/{job.total_items} 题已完成</strong>
                <span>{job.provider} · {job.model} · {job.status}</span>
              </div>
              <button
                className="primary-button"
                type="button"
                disabled={busy === job.id || !["pending", "running", "partial"].includes(job.status)}
                onClick={() => void resume(job)}
              >
                {busy === job.id ? "处理中…" : job.status === "completed" ? "已完成" : "继续处理 1 题"}
              </button>
            </header>
            <div className="durable-ai-item-strip">
              {job.items.map((item) => (
                <span className={item.status} key={item.id} title={item.error_message || item.status}>
                  Q{item.question_number || "?"}
                </span>
              ))}
            </div>
          </article>
        ))}
        {!jobs.length ? <p>还没有逐题任务。你可以先创建队列，确认后再逐题处理。</p> : null}
      </div>
    </section>
  );
}
