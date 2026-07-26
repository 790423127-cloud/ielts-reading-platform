"use client";

import { useEffect, useMemo, useState } from "react";

import {
  capturePersonalSentence,
  deletePersonalSentence,
  fetchPersonalSentences,
  fetchSentenceTraining,
  submitSentenceTraining,
  updatePersonalSentenceAnalysis,
  type PersonalSentence,
  type PersonalSentenceAnalysis,
  type SentenceTrainingAttempt,
  type SentenceTrainingCatalog
} from "@/lib/learningApi";

type Tab = "fixed" | "personal";
type FiveStepAnswers = {
  predicate: string;
  subject: string;
  object: string;
  scope: string;
  logic: string;
};

const EMPTY_STEPS: FiveStepAnswers = {
  predicate: "",
  subject: "",
  object: "",
  scope: "",
  logic: ""
};

const LOGIC_OPTIONS = [
  ["", "请选择逻辑关系"],
  ["none", "无明显逻辑连接"],
  ["contrast", "转折"],
  ["cause_effect", "因果"],
  ["condition", "条件"],
  ["time", "时间"],
  ["purpose", "目的"],
  ["comparison", "比较"],
  ["addition", "并列/递进"],
  ["restriction", "限定"]
] as const;

function newSubmissionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `sentence-${crypto.randomUUID()}`;
  }
  return `sentence-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function sourceLabel(sourceType: PersonalSentence["source_type"]): string {
  return {
    manual: "手工粘贴",
    reading_selection: "阅读选句",
    wrong_evidence: "错题定位句",
    mock_mark: "模考标记"
  }[sourceType];
}

function permissionLabel(permission: PersonalSentence["permission"]): string {
  return {
    locked: "仅保存，交卷后分析",
    self_only: "自我拆解",
    verified: "有审核标准"
  }[permission];
}

export default function SentenceLearningCenter() {
  const [tab, setTab] = useState<Tab>("fixed");
  const [catalog, setCatalog] = useState<SentenceTrainingCatalog | null>(null);
  const [personal, setPersonal] = useState<PersonalSentence[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [fixedAnswers, setFixedAnswers] = useState<FiveStepAnswers>(EMPTY_STEPS);
  const [fixedAttempt, setFixedAttempt] = useState<SentenceTrainingAttempt | null>(null);
  const [selectedPersonalId, setSelectedPersonalId] = useState("");
  const [personalAnalysis, setPersonalAnalysis] = useState<PersonalSentenceAnalysis>({});
  const [manualSentence, setManualSentence] = useState("");
  const [manualPrevious, setManualPrevious] = useState("");
  const [manualNext, setManualNext] = useState("");
  const [manualParagraph, setManualParagraph] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refreshPersonal() {
    const items = await fetchPersonalSentences("owner");
    setPersonal(items);
    if (!selectedPersonalId && items[0]) {
      setSelectedPersonalId(items[0].id);
      setPersonalAnalysis(items[0].analysis || {});
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchSentenceTraining(controller.signal),
      fetchPersonalSentences("owner", controller.signal)
    ])
      .then(([training, sentences]) => {
        setCatalog(training);
        setPersonal(sentences);
        if (sentences[0]) {
          setSelectedPersonalId(sentences[0].id);
          setPersonalAnalysis(sentences[0].analysis || {});
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "长难句数据读取失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const activeItem = catalog?.items[activeIndex];
  const selectedPersonal = useMemo(
    () => personal.find((item) => item.id === selectedPersonalId) || personal[0],
    [personal, selectedPersonalId]
  );

  function selectPersonal(item: PersonalSentence) {
    setSelectedPersonalId(item.id);
    setPersonalAnalysis(item.analysis || {});
    setNotice("");
    setError("");
  }

  async function submitFixed() {
    if (!activeItem || saving) return;
    setSaving(true);
    setError("");
    try {
      const attempt = await submitSentenceTraining({
        user_id: "owner",
        client_submission_id: newSubmissionId(),
        item_id: activeItem.id,
        answers: fixedAnswers
      });
      setFixedAttempt(attempt);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "固定训练提交失败");
    } finally {
      setSaving(false);
    }
  }

  function nextFixed() {
    if (!catalog?.items.length) return;
    setActiveIndex((index) => (index + 1) % catalog.items.length);
    setFixedAnswers(EMPTY_STEPS);
    setFixedAttempt(null);
    setError("");
  }

  async function addManual() {
    if (!manualSentence.trim() || saving) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const item = await capturePersonalSentence({
        user_id: "owner",
        sentence: manualSentence.trim(),
        previous_sentence: manualPrevious.trim() || undefined,
        next_sentence: manualNext.trim() || undefined,
        paragraph: manualParagraph.trim() || undefined,
        source_type: "manual"
      });
      await refreshPersonal();
      setSelectedPersonalId(item.id);
      setPersonalAnalysis(item.analysis || {});
      setManualSentence("");
      setManualPrevious("");
      setManualNext("");
      setManualParagraph("");
      setNotice(item.deduplicated ? "这条句子已经存在，已定位到原记录。" : "已加入我的句子。手工句子只作为自我拆解，不会显示标准答案。" );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "句子保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function savePersonalAnalysis() {
    if (!selectedPersonal || !selectedPersonal.analysis_allowed || saving) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const updated = await updatePersonalSentenceAnalysis(
        selectedPersonal.id,
        personalAnalysis,
        "owner"
      );
      setPersonal((items) => items.map((item) => item.id === updated.id ? updated : item));
      setPersonalAnalysis(updated.analysis || {});
      setNotice("五步自我拆解已保存。" );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "自我拆解保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function removePersonal() {
    if (!selectedPersonal || saving) return;
    if (!window.confirm("确定删除这条个人句子和自我拆解吗？")) return;
    setSaving(true);
    try {
      await deletePersonalSentence(selectedPersonal.id, "owner");
      const remaining = personal.filter((item) => item.id !== selectedPersonal.id);
      setPersonal(remaining);
      setSelectedPersonalId(remaining[0]?.id || "");
      setPersonalAnalysis(remaining[0]?.analysis || {});
      setNotice("个人句子已删除。" );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap sentence-learning-page">
      <header className="page-heading">
        <p className="eyebrow">SENTENCE WORKBENCH</p>
        <h1>长难句训练与我的句子</h1>
        <p>固定训练使用30条审核句子和确定性五步判分；我的句子保留来源与上下文，未审核文本只做自我拆解，不冒充标准答案。</p>
      </header>
      {error ? <div className="page-error">{error}</div> : null}
      {notice ? <div className="sentence-notice">{notice}</div> : null}

      <section className="sentence-policy-strip">
        <article><span>审核固定句</span><strong>{catalog?.status.item_count || 30}</strong></article>
        <article><span>分析步骤</span><strong>5步</strong></article>
        <article><span>固定训练AI</span><strong>0</strong></article>
        <article><span>未审核标准拆解</span><strong>不提供</strong></article>
      </section>

      <div className="sentence-tabs" role="tablist" aria-label="长难句模式">
        <button type="button" className={tab === "fixed" ? "active" : ""} onClick={() => setTab("fixed")}>固定训练</button>
        <button type="button" className={tab === "personal" ? "active" : ""} onClick={() => setTab("personal")}>我的句子 <span>{personal.length}</span></button>
      </div>

      {loading ? <div className="sentence-loading">正在读取长难句训练数据…</div> : tab === "fixed" ? (
        <section className="fixed-sentence-layout">
          <aside className="fixed-sentence-list" aria-label="审核句子列表">
            {catalog?.items.map((item, index) => (
              <button type="button" key={item.id} className={index === activeIndex ? "active" : ""} onClick={() => { setActiveIndex(index); setFixedAnswers(EMPTY_STEPS); setFixedAttempt(null); }}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><strong>{item.sentence}</strong><small>{item.difficulty} · verified</small></div>
              </button>
            ))}
          </aside>
          {activeItem ? (
            <article className="fixed-sentence-workbench">
              <div className="sentence-source-row"><span>审核训练句 {activeIndex + 1}/{catalog?.items.length}</span><small>答案在提交前不会下发</small></div>
              <blockquote className="training-sentence">{activeItem.sentence}</blockquote>
              <div className="five-step-form">
                {(catalog?.steps || []).map((step) => {
                  const resultRow = fixedAttempt?.result.steps.find((row) => row.key === step.key);
                  return (
                    <label key={step.key} className={resultRow ? (resultRow.correct ? "step-correct" : "step-wrong") : ""}>
                      <span><b>{step.label}</b><small>{step.prompt}</small></span>
                      {step.key === "logic" ? (
                        <select disabled={Boolean(fixedAttempt)} value={fixedAnswers.logic} onChange={(event) => setFixedAnswers((current) => ({ ...current, logic: event.target.value }))}>
                          {LOGIC_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                        </select>
                      ) : (
                        <textarea disabled={Boolean(fixedAttempt)} rows={2} value={fixedAnswers[step.key]} onChange={(event) => setFixedAnswers((current) => ({ ...current, [step.key]: event.target.value }))} placeholder={step.key === "object" || step.key === "scope" ? "没有时可留空" : "输入你识别的原文片段"} />
                      )}
                      {resultRow ? <div className="step-feedback"><strong>{resultRow.correct ? "正确" : "需要修正"}</strong><span>审核标准：{resultRow.expected_answer || "无"}</span></div> : null}
                    </label>
                  );
                })}
              </div>
              {fixedAttempt ? (
                <section className="fixed-sentence-result">
                  <div><span>五步得分</span><strong>{fixedAttempt.result.score}/{fixedAttempt.result.total}</strong><small>{fixedAttempt.result.accuracy}%</small></div>
                  <div><h3>审核讲解</h3><p>{fixedAttempt.result.explanation}</p>{fixedAttempt.result.simplified_zh ? <p><b>简化理解：</b>{fixedAttempt.result.simplified_zh}</p> : null}{fixedAttempt.result.answer_impact ? <p><b>对答题的影响：</b>{fixedAttempt.result.answer_impact}</p> : null}</div>
                </section>
              ) : null}
              <div className="sentence-workbench-actions">
                {fixedAttempt ? <button type="button" className="primary-button" onClick={nextFixed}>下一条审核句</button> : <button type="button" className="primary-button" disabled={saving} onClick={() => void submitFixed()}>{saving ? "正在判分…" : "提交五步拆解"}</button>}
              </div>
            </article>
          ) : null}
        </section>
      ) : (
        <section className="personal-sentence-section">
          <article className="manual-sentence-form">
            <div><span>MANUAL CAPTURE</span><h2>加入我的句子</h2><p>手工粘贴仅用于保存和自我拆解，不会自动获得审核标准或AI分析。</p></div>
            <label><span>句子</span><textarea rows={4} value={manualSentence} onChange={(event) => setManualSentence(event.target.value)} placeholder="粘贴需要拆解的英文长难句" /></label>
            <div className="manual-context-grid">
              <label><span>上一句（可选）</span><textarea rows={2} value={manualPrevious} onChange={(event) => setManualPrevious(event.target.value)} /></label>
              <label><span>下一句（可选）</span><textarea rows={2} value={manualNext} onChange={(event) => setManualNext(event.target.value)} /></label>
            </div>
            <label><span>所在段落（可选）</span><textarea rows={3} value={manualParagraph} onChange={(event) => setManualParagraph(event.target.value)} /></label>
            <button type="button" className="primary-button" disabled={saving || !manualSentence.trim()} onClick={() => void addManual()}>{saving ? "正在保存…" : "加入我的句子"}</button>
          </article>

          <div className="personal-sentence-layout">
            <aside className="personal-sentence-list">
              {personal.length ? personal.map((item) => (
                <button type="button" key={item.id} className={item.id === selectedPersonal?.id ? "active" : ""} onClick={() => selectPersonal(item)}>
                  <span>{sourceLabel(item.source_type)}</span>
                  <strong>{item.sentence}</strong>
                  <small>{permissionLabel(item.permission)} · {formatDate(item.updated_at)}</small>
                </button>
              )) : <div className="personal-empty">还没有个人句子。可在上方粘贴，或从错题定位句加入。</div>}
            </aside>

            {selectedPersonal ? (
              <article className="personal-sentence-editor">
                <div className="personal-sentence-head">
                  <div><span>{sourceLabel(selectedPersonal.source_type)}</span><h2>{selectedPersonal.sentence}</h2><small>{selectedPersonal.test_title || selectedPersonal.test_id || "个人内容"}{selectedPersonal.part_number ? ` · Part ${selectedPersonal.part_number}` : ""}</small></div>
                  <div className={`permission-badge ${selectedPersonal.permission}`}>{permissionLabel(selectedPersonal.permission)}</div>
                </div>
                {selectedPersonal.previous_sentence || selectedPersonal.next_sentence || selectedPersonal.paragraph ? (
                  <details className="sentence-context" open>
                    <summary>查看来源上下文</summary>
                    {selectedPersonal.previous_sentence ? <p><b>上一句：</b>{selectedPersonal.previous_sentence}</p> : null}
                    {selectedPersonal.paragraph ? <p><b>段落：</b>{selectedPersonal.paragraph}</p> : null}
                    {selectedPersonal.next_sentence ? <p><b>下一句：</b>{selectedPersonal.next_sentence}</p> : null}
                  </details>
                ) : null}

                {selectedPersonal.permission === "locked" ? (
                  <div className="sentence-locked-note"><strong>当前只保存标记</strong><p>来源尚未绑定已交卷Session，不能进行拆解，也不会显示答案或解析。</p></div>
                ) : (
                  <div className="personal-analysis-form">
                    <h3>我的五步拆解</h3>
                    <label><span>谓语</span><textarea rows={2} value={personalAnalysis.predicate || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, predicate: event.target.value }))} /></label>
                    <label><span>主语</span><textarea rows={2} value={personalAnalysis.subject || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, subject: event.target.value }))} /></label>
                    <label><span>宾语或补语</span><textarea rows={2} value={personalAnalysis.object || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, object: event.target.value }))} /></label>
                    <label><span>修饰与范围</span><textarea rows={2} value={personalAnalysis.scope || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, scope: event.target.value }))} /></label>
                    <label><span>逻辑</span><select value={personalAnalysis.logic || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, logic: event.target.value }))}>{LOGIC_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                    <label><span>我的笔记</span><textarea rows={4} value={personalAnalysis.note || ""} onChange={(event) => setPersonalAnalysis((current) => ({ ...current, note: event.target.value }))} /></label>
                    <button type="button" className="primary-button" disabled={saving} onClick={() => void savePersonalAnalysis()}>{saving ? "正在保存…" : "保存自我拆解"}</button>
                  </div>
                )}

                {selectedPersonal.standard_parse ? (
                  <section className="verified-standard-parse">
                    <div><span>VERIFIED STANDARD</span><h3>审核标准拆解</h3></div>
                    <dl>
                      <div><dt>谓语</dt><dd>{selectedPersonal.standard_parse.predicate}</dd></div>
                      <div><dt>主语</dt><dd>{selectedPersonal.standard_parse.subject}</dd></div>
                      <div><dt>宾语/补语</dt><dd>{selectedPersonal.standard_parse.object || "无"}</dd></div>
                      <div><dt>修饰与范围</dt><dd>{selectedPersonal.standard_parse.scope || "无"}</dd></div>
                      <div><dt>逻辑</dt><dd>{selectedPersonal.standard_parse.logic}</dd></div>
                    </dl>
                    <p>{selectedPersonal.standard_parse.explanation}</p>
                  </section>
                ) : selectedPersonal.permission !== "locked" ? (
                  <div className="unverified-parse-note"><strong>没有审核标准拆解</strong><p>这条句子可以保存你的自我分析，但系统不会把自动猜测标成标准答案。</p></div>
                ) : null}

                <div className="personal-danger-row"><button type="button" disabled={saving} onClick={() => void removePersonal()}>删除这条句子</button></div>
              </article>
            ) : <div className="personal-editor-empty">选择或添加一条句子开始拆解。</div>}
          </div>
        </section>
      )}
    </div>
  );
}
