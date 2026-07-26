"use client";

import { useEffect, useMemo, useState } from "react";

import AiTeacherPanel from "@/components/AiTeacherPanel";
import { fetchPersonalSentences, type PersonalSentence } from "@/lib/learningApi";

export default function SentenceAiTeacherCenter() {
  const [items, setItems] = useState<PersonalSentence[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetchPersonalSentences("owner", controller.signal)
      .then((sentences) => {
        const available = sentences.filter((item) => item.permission !== "locked");
        setItems(available);
        setSelectedId(available[0]?.id || "");
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "句子读取失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || items[0],
    [items, selectedId]
  );

  return (
    <section className="page-wrap ai-page-section">
      <div className="section-title-row">
        <div><span>AI SENTENCE TEACHER</span><h2>针对我的句子继续提问</h2></div>
        <small>未交卷锁定句不会进入AI分析。</small>
      </div>
      {error ? <div className="page-error">{error}</div> : null}
      {loading ? <div className="ai-teacher-loading">正在读取可分析的个人句子…</div> : items.length ? (
        <>
          <label className="ai-context-selector">
            <span>选择句子</span>
            <select value={selected?.id || ""} onChange={(event) => setSelectedId(event.target.value)}>
              {items.map((item) => (
                <option key={item.id} value={item.id}>{item.sentence.slice(0, 100)}</option>
              ))}
            </select>
          </label>
          {selected ? (
            <AiTeacherPanel
              key={selected.id}
              contextType="sentence"
              sentenceId={selected.id}
              title="问这条长难句"
              description={selected.permission === "verified" ? "这条句子有审核标准，AI会结合标准拆解解释。" : "这条句子没有审核标准，AI只提供学习分析，不会把推断冒充标准答案。"}
              suggestions={["这句话的主干是什么？", "修饰成分分别修饰什么？", "请按意群解释并给出中文理解。"]}
            />
          ) : null}
        </>
      ) : <div className="ai-teacher-empty">目前没有可分析的个人句子。先在上方加入句子；模考中保存的锁定句需要交卷后才能分析。</div>}
    </section>
  );
}
