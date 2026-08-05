"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  chatWithAiTeacher,
  deleteAiConversation,
  fetchAiConversations,
  type AiTeacherContextType,
  type AiTeacherConversation
} from "@/lib/aiTeacherApi";

type Props = {
  contextType: AiTeacherContextType;
  sessionId?: string;
  questionId?: string;
  sentenceId?: string;
  title?: string;
  description?: string;
  suggestions?: string[];
};

function contextRef(props: Props): string {
  if (props.contextType === "wrong_question") return `${props.sessionId || ""}:${props.questionId || ""}`;
  if (props.contextType === "sentence") return props.sentenceId || "";
  return "current";
}

export default function AiTeacherPanel(props: Props) {
  const [conversation, setConversation] = useState<AiTeacherConversation | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const expectedRef = contextRef({
    contextType: props.contextType,
    sessionId: props.sessionId,
    questionId: props.questionId,
    sentenceId: props.sentenceId
  });

  useEffect(() => {
    const controller = new AbortController();
    setConversation(null);
    setError("");
    setLoading(true);
    fetchAiConversations("owner", controller.signal)
      .then((items) => {
        const matched = items.find(
          (item) => item.context_type === props.contextType && item.context_ref === expectedRef
        );
        setConversation(matched || null);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "AI对话记录读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [props.contextType, expectedRef]);

  async function submit(event?: FormEvent<HTMLFormElement>, preset?: string) {
    event?.preventDefault();
    const content = (preset ?? question).trim();
    if (!content || sending) return;
    setSending(true);
    setError("");
    try {
      const response = await chatWithAiTeacher({
        context_type: props.contextType,
        question: content,
        session_id: props.sessionId,
        question_id: props.questionId,
        sentence_id: props.sentenceId
      });
      setConversation(response.conversation);
      setQuestion("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "AI老师回答失败");
    } finally {
      setSending(false);
    }
  }

  async function clearConversation() {
    if (!conversation || sending) return;
    if (!window.confirm("确定清空这个学习位置的AI对话记录吗？")) return;
    setSending(true);
    setError("");
    try {
      await deleteAiConversation(conversation.id);
      setConversation(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "清空对话失败");
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="ai-teacher-panel">
      <div className="ai-teacher-heading">
        <div>
          <span>AI LEARNING TEACHER</span>
          <h3>{props.title || "问AI学习老师"}</h3>
          <p>{props.description || "AI只解释服务端提供的学习证据，不能修改答案、分数、Band或掌握状态。"}</p>
        </div>
        {conversation ? <button type="button" onClick={() => void clearConversation()} disabled={sending}>清空对话</button> : null}
      </div>

      <div className="ai-teacher-guardrail">
        <span>只读解释</span>
        <span>不改判分</span>
        <span>不标记掌握</span>
        <span>无证据不编造</span>
      </div>

      {loading ? <div className="ai-teacher-loading">正在读取这个学习位置的对话…</div> : null}
      {!loading && conversation?.messages.length ? (
        <div className="ai-teacher-messages" aria-live="polite">
          {conversation.messages.map((message) => (
            <article className={`ai-message ${message.role}`} key={message.id}>
              <span>{message.role === "user" ? "我" : "AI老师"}</span>
              <p>{message.content}</p>
              {message.role === "assistant" ? (
                <small>{message.cached ? "缓存回答 · 未新增调用" : `${message.model || "AI"} · ${message.input_tokens + message.output_tokens} tokens`}</small>
              ) : null}
            </article>
          ))}
        </div>
      ) : !loading ? <div className="ai-teacher-empty">还没有对话。可以直接选择下面的问题，或输入你不理解的地方。</div> : null}

      {props.suggestions?.length ? (
        <div className="ai-teacher-suggestions">
          {props.suggestions.map((suggestion) => (
            <button key={suggestion} type="button" disabled={sending} onClick={() => void submit(undefined, suggestion)}>{suggestion}</button>
          ))}
        </div>
      ) : null}

      <form className="ai-teacher-form" onSubmit={(event) => void submit(event)}>
        <textarea
          rows={3}
          maxLength={3000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="输入具体问题，例如：题干和原文的矛盾在哪里？"
        />
        <button className="primary-button" type="submit" disabled={sending || !question.trim()}>{sending ? "正在分析…" : "发送问题"}</button>
      </form>
      {error ? <div className="ai-teacher-error">{error}</div> : null}
      {conversation ? (
        <div className="ai-teacher-usage">
          <span>实际调用 {conversation.usage.provider_calls} 次</span>
          <span>缓存命中 {conversation.usage.cache_hits} 次</span>
          <span>累计 {conversation.usage.input_tokens + conversation.usage.output_tokens} tokens</span>
        </div>
      ) : null}
    </section>
  );
}
