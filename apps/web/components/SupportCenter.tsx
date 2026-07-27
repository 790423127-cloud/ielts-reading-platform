"use client";

import { useEffect, useState } from "react";

import { fetchAiProviderStatus, type AiProviderStatus } from "@/lib/api";

export default function SupportCenter() {
  const [fontSize, setFontSize] = useState("22");
  const [provider, setProvider] = useState<AiProviderStatus | null>(null);
  useEffect(() => {
    setFontSize(localStorage.getItem("ielts-passage-font-size") || "22");
    const controller = new AbortController();
    void fetchAiProviderStatus(controller.signal).then(setProvider).catch(() => null);
    return () => controller.abort();
  }, []);
  function saveSize(value: string) {
    setFontSize(value);
    localStorage.setItem("ielts-passage-font-size", value);
  }
  function exportFeedback() {
    const payload = {
      created_at: new Date().toISOString(),
      page: window.location.href,
      user_agent: navigator.userAgent,
      note: "请在这里补充问题描述与复现步骤"
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "ielts-feedback-template.json"; anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="page-wrap support-page">
      <header className="page-heading"><p className="eyebrow">SETTINGS · HELP · FEEDBACK</p><h1>设置、帮助与反馈</h1><p>这里仅管理本机显示偏好并提供可离线保存的反馈模板，不上传任何学习数据。</p></header>
      <div className="support-grid">
        <article><h2>阅读显示</h2><label><span>默认文章字号</span><select value={fontSize} onChange={(event) => saveSize(event.target.value)}>{[18,20,22,24,26].map((size) => <option key={size}>{size}</option>)}</select></label><p>机考页仍可用 A− / A+ 临时调整，偏好保存在本机浏览器。</p></article>
        <article><h2>AI 与隐私</h2><p>当前：{provider?.selected_label || "未读取"} · {provider?.model || "—"} · {provider?.configured ? "已配置" : "未配置"}</p><p>判分、错题与阶段报告不依赖 AI；只有明确点击 AI 辅助时才可能调用模型。</p></article>
        <article><h2>机考帮助</h2><ul><li>黄色标记表示你主动标记的题目。</li><li>草稿会自动保存在本机，不会提交判分。</li><li>暂停只冻结计时，不会清空答案。</li><li>交卷后才会显示答案与解析。</li></ul></article>
        <article><h2>反馈</h2><p>系统当前没有外部反馈账号，避免把隐私数据发送到未知位置。可下载模板后自行补充并交给开发人员。</p><button type="button" className="secondary-button" onClick={exportFeedback}>下载反馈模板</button></article>
      </div>
    </section>
  );
}
