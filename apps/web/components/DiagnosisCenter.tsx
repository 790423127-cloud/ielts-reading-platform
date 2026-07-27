"use client";

import { useEffect, useState } from "react";

import { fetchAiProviderStatus, fetchStageReport, type AiProviderStatus, type StageReport } from "@/lib/api";

export default function DiagnosisCenter() {
  const [report, setReport] = useState<StageReport | null>(null);
  const [provider, setProvider] = useState<AiProviderStatus | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([fetchStageReport("owner", controller.signal), fetchAiProviderStatus(controller.signal)])
      .then(([nextReport, nextProvider]) => { setReport(nextReport); setProvider(nextProvider); })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "诊断数据读取失败"); });
    return () => controller.abort();
  }, []);
  return (
    <section className="page-wrap diagnosis-page">
      <header className="page-heading"><p className="eyebrow">EVIDENCE-BASED DIAGNOSIS</p><h1>学习诊断与模型状态</h1><p>先显示可复核的练习数据，再说明 AI 配置。这里不会自动产生付费调用，诊断建议也不等于 IELTS 官方评分。</p></header>
      {error ? <div className="page-error">{error}</div> : null}
      <section className="provider-status-card">
        <div><span className={provider?.configured ? "status-dot ready" : "status-dot"} /><div><span>当前 AI 助教</span><strong>{provider?.selected_label || "正在读取"}</strong><small>{provider?.model || "—"}</small></div></div>
        <strong>{provider?.configured ? "已配置，可在明确场景手动使用" : "未配置；不影响判分和确定性报告"}</strong>
      </section>
      <section className="diagnosis-summary-grid">
        <article><span>数据样本</span><strong>{report?.summary.session_count || 0} 次</strong></article>
        <article><span>累计题量</span><strong>{report?.summary.total_questions || 0} 题</strong></article>
        <article><span>总体正确率</span><strong>{report?.summary.accuracy || 0}%</strong></article>
        <article><span>本页 AI 调用</span><strong>0</strong></article>
      </section>
      <section className="diagnosis-insights"><h2>基于证据的阶段判断</h2>
        {report?.deterministic_interpretation.length ? report.deterministic_interpretation.map((text) => <p key={text}>{text}</p>) : <p>数据不足。先完成至少 5 题，系统才显示初步倾向；至少 10 题才视为较稳定样本。</p>}
      </section>
    </section>
  );
}
