"use client";

import { useEffect, useMemo, useState } from "react";

import AiTeacherPanel from "@/components/AiTeacherPanel";
import { fetchWrongQuestions, type WrongReviewItem } from "@/lib/api";

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
                return <option key={key} value={key}>Q{item.number} · {item.question_subtype} · {item.prompt.slice(0, 90)}</option>;
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
    </section>
  );
}
