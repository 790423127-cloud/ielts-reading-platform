"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  captureVocabulary,
  acknowledgeVocabularySmartSync,
  deleteVocabulary,
  exportParaphraseSelection,
  exportVocabularySelection,
  fetchParaphrases,
  fetchVocabulary,
  prepareVocabularySmartSync,
  updateParaphraseStatus,
  updateVocabulary,
  vocabularyExportUrl,
  type ParaphraseItem,
  type SmartSyncReceiptItem,
  type VocabularyItem
} from "@/lib/learningApi";

const STATUS_LABELS = {
  learning: "学习中",
  mastered: "已掌握"
} as const;

const PARAPHRASE_RELATION_LABELS: Record<ParaphraseItem["relation_type"], string> = {
  "direct-paraphrase": "直接同义",
  "near-paraphrase": "近义替换",
  "contextual-paraphrase": "语境对应",
  "curated-paraphrase": "题库核验"
};

const SOURCE_LABELS: Record<string, string> = {
  reading_text: "阅读原文",
  question: "题目",
  option: "选项",
  wrong_review: "错题解析",
  sentence: "长难句",
  ai: "AI解释",
  manual: "手动添加"
};

type EditState = {
  id: string;
  meaning: string;
  note: string;
  status: "learning" | "mastered";
};

function downloadFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function articleCount(item: VocabularyItem): number {
  const articleKeys = new Set<string>();
  for (const source of item.sources) {
    if (source.source_type !== "reading_text" || !source.part_number) continue;
    const testKey = String(source.test_id || source.test_title || "").trim().toLocaleLowerCase();
    if (testKey) articleKeys.add(`${testKey}:${source.part_number}`);
  }
  return articleKeys.size;
}

function paraphraseArticleCount(item: ParaphraseItem): number {
  const articleKeys = new Set<string>();
  for (const source of item.sources) {
    if (!source.part_number) continue;
    const testKey = String(source.test_id || source.test_title || "").trim().toLocaleLowerCase();
    if (testKey) articleKeys.add(`${testKey}:${source.part_number}`);
  }
  return articleKeys.size;
}

export default function VocabularyCenter() {
  const [items, setItems] = useState<VocabularyItem[]>([]);
  const [paraphrases, setParaphrases] = useState<ParaphraseItem[]>([]);
  const [activeTab, setActiveTab] = useState<"words" | "paraphrases">("words");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState("");
  const [wordLoadError, setWordLoadError] = useState("");
  const [paraphraseLoadError, setParaphraseLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "learning" | "mastered">("all");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedParaphraseIds, setSelectedParaphraseIds] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<EditState | null>(null);
  const [draft, setDraft] = useState({
    term: "",
    meaning: "",
    note: "",
    source_sentence: ""
  });

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      fetchVocabulary("owner", controller.signal),
      fetchParaphrases("owner", controller.signal)
    ])
      .then(([wordResult, paraphraseResult]) => {
        if (controller.signal.aborted) return;
        if (wordResult.status === "fulfilled") {
          setItems(wordResult.value);
          setWordLoadError("");
        } else {
          setWordLoadError(wordResult.reason instanceof Error ? wordResult.reason.message : "生词记录读取失败");
        }
        if (paraphraseResult.status === "fulfilled") {
          setParaphrases(paraphraseResult.value);
          setParaphraseLoadError("");
        } else {
          setParaphraseLoadError(
            paraphraseResult.reason instanceof Error
              ? paraphraseResult.reason.message
              : "错题同义替换读取失败"
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return items.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (!normalized) return true;
      return [item.term, item.meaning, item.note]
        .some((value) => value.toLocaleLowerCase().includes(normalized));
    });
  }, [items, query, statusFilter]);

  const visibleParaphrases = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return paraphrases.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) return false;
      if (!normalized) return true;
      return [item.question_phrase, item.source_phrase, item.note]
        .some((value) => value.toLocaleLowerCase().includes(normalized));
    });
  }, [paraphrases, query, statusFilter]);

  const learningCount = items.filter((item) => item.status === "learning").length;
  const masteredCount = items.length - learningCount;
  const occurrenceCount = items.reduce((total, item) => total + item.occurrence_count, 0);
  const unexportedCount = items.filter((item) => !item.exported_before).length;
  const paraphraseUnexportedCount = paraphrases.filter((item) => !item.exported_before).length;
  const paraphraseOccurrenceCount = paraphrases.reduce((total, item) => total + item.occurrence_count, 0);

  async function refreshVocabulary() {
    const refreshed = await fetchVocabulary();
    setItems(refreshed);
  }

  async function refreshParaphrases() {
    const refreshed = await fetchParaphrases();
    setParaphrases(refreshed);
  }

  async function syncToVocabularyApp() {
    const targetOrigin = (
      process.env.NEXT_PUBLIC_VOCABULARY_APP_ORIGIN || "http://localhost:3000"
    ).replace(/\/+$/, "");
    let popup: Window | null = null;
    let prepared: Awaited<ReturnType<typeof prepareVocabularySmartSync>> | null = null;
    let targetReady = false;
    let timeoutId: number | undefined;
    let messageHandler: ((event: MessageEvent) => void) | undefined;
    const cleanup = () => {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      if (messageHandler) window.removeEventListener("message", messageHandler);
    };
    setSyncing(true);
    setError("");
    setNotice("");
    try {
      const resultPromise = new Promise<{
        transferId: string;
        receipt: { words: SmartSyncReceiptItem[]; paraphrases: SmartSyncReceiptItem[] };
        summary?: Record<string, number>;
      }>((resolve, reject) => {
        const sendWhenReady = () => {
          if (targetReady && prepared && popup) popup.postMessage(prepared, targetOrigin);
        };
        messageHandler = (event: MessageEvent) => {
          if (event.origin !== targetOrigin || event.source !== popup) return;
          if (event.data?.type === "ielts-reading-coach-smart-sync-ready") {
            targetReady = true;
            sendWhenReady();
            return;
          }
          if (
            event.data?.type !== "ielts-reading-coach-smart-sync-result"
            || !prepared
            || event.data?.transferId !== prepared.transferId
          ) return;
          if (event.data.status !== "ok") {
            reject(new Error(String(event.data?.message || "词库软件写入失败")));
            return;
          }
          resolve(event.data);
        };
        window.addEventListener("message", messageHandler);
        timeoutId = window.setTimeout(
          () => reject(new Error("词库软件没有响应，请确认它已启动后重试")),
          20000
        );
      });

      popup = window.open(
        `${targetOrigin}/reading-sync?sourceOrigin=${encodeURIComponent(window.location.origin)}`,
        "ielts-vocabulary-smart-sync",
        "popup=yes,width=860,height=720"
      );
      if (!popup) throw new Error("浏览器拦截了传输窗口，请允许弹窗后重试");
      prepared = await prepareVocabularySmartSync();
      if (prepared.counts.words + prepared.counts.paraphrases === 0) {
        popup.close();
        setNotice("没有新增或变更内容；以前传过的记录没有重复发送。");
        return;
      }
      if (targetReady) popup.postMessage(prepared, targetOrigin);
      const result = await resultPromise;
      const acknowledgement = await acknowledgeVocabularySmartSync({
        transfer_id: result.transferId,
        words: result.receipt.words,
        paraphrases: result.receipt.paraphrases
      });
      await Promise.all([refreshVocabulary(), refreshParaphrases()]);
      const staleCount = acknowledgement.stale_word_ids.length + acknowledgement.stale_paraphrase_ids.length;
      setNotice(
        `已传到词库软件：生词 ${acknowledgement.words_marked} 条，同义替换 ${acknowledgement.paraphrases_marked} 条。`
        + (staleCount ? `另有 ${staleCount} 条在传输期间发生变化，下次会自动补传。` : "重复内容已自动跳过。")
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "传输失败");
    } finally {
      cleanup();
      setSyncing(false);
    }
  }

  async function submitNewItem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft.term.trim()) return;
    setSaving(true);
    setError("");
    try {
      const saved = await captureVocabulary({
        term: draft.term,
        meaning: draft.meaning,
        note: draft.note,
        source_type: "manual",
        source_sentence: draft.source_sentence || undefined
      });
      setItems((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      setDraft({ term: "", meaning: "", note: "", source_sentence: "" });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存词汇失败");
    } finally {
      setSaving(false);
    }
  }

  function beginEdit(item: VocabularyItem) {
    setEditing({
      id: item.id,
      meaning: item.meaning,
      note: item.note,
      status: item.status
    });
  }

  async function saveEdit() {
    if (!editing) return;
    setSaving(true);
    setError("");
    try {
      const saved = await updateVocabulary(editing.id, {
        meaning: editing.meaning,
        note: editing.note,
        status: editing.status
      });
      setItems((current) => current.map((item) => item.id === saved.id ? saved : item));
      setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新词汇失败");
    } finally {
      setSaving(false);
    }
  }

  async function markParaphraseStatus(item: ParaphraseItem, status: ParaphraseItem["status"]) {
    setSaving(true);
    setError("");
    try {
      const saved = await updateParaphraseStatus(item.id, status);
      setParaphrases((current) => current.map((row) => row.id === saved.id ? saved : row));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "更新同义替换状态失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeItem(item: VocabularyItem) {
    if (!window.confirm(`确定永久删除“${item.term}”吗？它的来源记录也会一起删除。`)) return;
    setSaving(true);
    setError("");
    try {
      await deleteVocabulary(item.id);
      setItems((current) => current.filter((row) => row.id !== item.id));
      setSelectedIds((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
      if (editing?.id === item.id) setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除词汇失败");
    } finally {
      setSaving(false);
    }
  }

  function toggleSelection(itemId: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  function toggleParaphraseSelection(itemId: string) {
    setSelectedParaphraseIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  async function exportWords(itemIds: string[], onlyUnexported: boolean) {
    if (!onlyUnexported && !itemIds.length) {
      setError("请先勾选要导出的单词。");
      return;
    }
    setExporting(true);
    setError("");
    setNotice("");
    try {
      const result = await exportVocabularySelection({
        item_ids: itemIds,
        only_unexported: onlyUnexported
      });
      downloadFile(result.blob, result.filename);
      await refreshVocabulary();
      setSelectedIds(new Set());
      setNotice(onlyUnexported ? "未导出的单词已保存为 TXT。" : "已选单词已保存为 TXT。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败");
    } finally {
      setExporting(false);
    }
  }

  async function exportParaphrases(itemIds: string[], onlyUnexported: boolean) {
    if (!onlyUnexported && !itemIds.length) {
      setError("请先勾选要导出的同义替换。");
      return;
    }
    setExporting(true);
    setError("");
    setNotice("");
    try {
      const result = await exportParaphraseSelection({
        item_ids: itemIds,
        only_unexported: onlyUnexported,
        format: "json"
      });
      downloadFile(result.blob, result.filename);
      await refreshParaphrases();
      setSelectedParaphraseIds(new Set());
      setNotice(onlyUnexported ? "未导出的同义替换学习包已保存为 JSON。" : "已选同义替换学习包已保存为 JSON。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导出失败");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="page-wrap vocabulary-page">
      <header className="page-heading vocabulary-heading">
        <div>
          <p className="eyebrow">PERSONAL VOCABULARY</p>
          <h1>我的词汇本</h1>
          <p>单词和错题同义替换分开记录；同一内容自动合并来源，跨文章复现或手动重复记录都会提示高频。</p>
        </div>
        <div className="vocabulary-export-actions">
          <button
            className="primary-button vocabulary-smart-sync-button"
            type="button"
            disabled={syncing || exporting}
            onClick={() => void syncToVocabularyApp()}
          >
            {syncing ? "正在传输…" : "智能传到词库软件"}
          </button>
          {activeTab === "words" ? (
            <>
              <button
                className="primary-button"
                type="button"
                disabled={exporting || unexportedCount === 0}
                onClick={() => void exportWords([], true)}
              >
                导出未导出（{unexportedCount}）
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={exporting || selectedIds.size === 0}
                onClick={() => void exportWords([...selectedIds], false)}
              >
                导出已选（{selectedIds.size}）
              </button>
              <a className="secondary-button" href={vocabularyExportUrl("json")}>备份 JSON</a>
            </>
          ) : (
            <>
              <button
                className="primary-button"
                type="button"
                disabled={exporting || paraphraseUnexportedCount === 0}
                onClick={() => void exportParaphrases([], true)}
              >
                导出未导出（{paraphraseUnexportedCount}）
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={exporting || selectedParaphraseIds.size === 0}
                onClick={() => void exportParaphrases([...selectedParaphraseIds], false)}
              >
                导出已选（{selectedParaphraseIds.size}）
              </button>
            </>
          )}
        </div>
      </header>

      {error ? <div className="page-error vocabulary-error">{error}</div> : null}
      {activeTab === "words" && wordLoadError ? (
        <div className="page-error vocabulary-error">生词接口暂不可用：{wordLoadError}</div>
      ) : null}
      {activeTab === "paraphrases" && paraphraseLoadError ? (
        <div className="page-error vocabulary-error">
          错题同义替换接口暂不可用，请确认新版后端已启动：{paraphraseLoadError}
        </div>
      ) : null}
      {notice ? <div className="vocabulary-notice">{notice}</div> : null}

      <div className="vocabulary-tabs" role="tablist" aria-label="词汇本分类">
        <button
          className={activeTab === "words" ? "active" : ""}
          type="button"
          onClick={() => setActiveTab("words")}
        >
          生词 <span>{items.length}</span>
        </button>
        <button
          className={activeTab === "paraphrases" ? "active" : ""}
          type="button"
          onClick={() => setActiveTab("paraphrases")}
        >
          错题同义替换 <span>{paraphrases.length}</span>
        </button>
      </div>

      <section className="vocabulary-stat-strip">
        {activeTab === "words" ? (
          <>
            <article><span>词汇总数</span><strong>{items.length}</strong></article>
            <article><span>学习中</span><strong>{learningCount}</strong></article>
            <article><span>已掌握</span><strong>{masteredCount}</strong></article>
            <article><span>累计来源</span><strong>{occurrenceCount}</strong></article>
          </>
        ) : (
          <>
            <article><span>同义替换</span><strong>{paraphrases.length}</strong></article>
            <article><span>未导出</span><strong>{paraphraseUnexportedCount}</strong></article>
            <article><span>学习中</span><strong>{paraphrases.filter((item) => item.status === "learning").length}</strong></article>
            <article><span>累计错题来源</span><strong>{paraphraseOccurrenceCount}</strong></article>
          </>
        )}
      </section>

      <section className="vocabulary-layout">
        <form className="vocabulary-capture-card" onSubmit={submitNewItem}>
          <div className="section-title-row">
            <div><span>{activeTab === "words" ? "QUICK CAPTURE" : "AUTO CAPTURE"}</span><h2>{activeTab === "words" ? "添加生词" : "错题自动记录"}</h2></div>
          </div>
          {activeTab === "words" ? (
            <>
              <label>
                <span>单词或词组 *</span>
                <input
                  value={draft.term}
                  onChange={(event) => setDraft((current) => ({ ...current, term: event.target.value }))}
                  placeholder="例如 substantial"
                  maxLength={300}
                  required
                />
              </label>
              <label>
                <span>中文释义</span>
                <textarea
                  value={draft.meaning}
                  onChange={(event) => setDraft((current) => ({ ...current, meaning: event.target.value }))}
                  placeholder="大量的；重要的"
                  rows={3}
                  maxLength={4000}
                />
              </label>
              <label>
                <span>原句或来源内容</span>
                <textarea
                  value={draft.source_sentence}
                  onChange={(event) => setDraft((current) => ({ ...current, source_sentence: event.target.value }))}
                  placeholder="粘贴这个词所在的原句"
                  rows={4}
                  maxLength={8000}
                />
              </label>
              <label>
                <span>个人笔记</span>
                <textarea
                  value={draft.note}
                  onChange={(event) => setDraft((current) => ({ ...current, note: event.target.value }))}
                  placeholder="搭配、易错点或记忆方法"
                  rows={4}
                  maxLength={8000}
                />
              </label>
              <button className="primary-button" type="submit" disabled={saving || !draft.term.trim()}>
                {saving ? "正在保存…" : "保存到词汇本"}
              </button>
              <p className="vocabulary-dedupe-note">重复收藏不会覆盖已有释义和笔记；手动重复保存会累计频率，新的原句会追加为新来源。</p>
            </>
          ) : (
            <div className="vocabulary-auto-note">
              <p>交卷后系统只读取错题，优先保存题库中已核验的“题目表达 = 原文表达”。</p>
              <p>本地资料不足时再由 AI 补充；AI 没配置或提取失败，也不会影响已保存的本地结果和判分。</p>
              <p>导出为 JSON 学习包，完整保留原题证据，可直接导入阅读同义替换记录本。</p>
            </div>
          )}
        </form>

        <div className="vocabulary-library">
          <div className="vocabulary-toolbar">
            <input
              aria-label={activeTab === "words" ? "搜索生词" : "搜索同义替换"}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={activeTab === "words" ? "搜索单词、释义或笔记" : "搜索题目表达、原文表达或笔记"}
            />
            <select aria-label="按状态筛选" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
              <option value="all">全部状态</option>
              <option value="learning">学习中</option>
              <option value="mastered">已掌握</option>
            </select>
            <span>{activeTab === "words" ? `显示 ${visibleItems.length}/${items.length}` : `显示 ${visibleParaphrases.length}/${paraphrases.length}`}</span>
          </div>

          {activeTab === "words" ? (
            loading ? <div className="vocabulary-loading">正在读取词汇本…</div> : visibleItems.length ? (
              <div className="vocabulary-list">
                {visibleItems.map((item) => {
                  const isEditing = editing?.id === item.id;
                  const distinctArticles = articleCount(item);
                  return (
                    <article className="vocabulary-card" key={item.id}>
                      <div className="vocabulary-card-heading">
                        <label className="vocabulary-card-select">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(item.id)}
                            onChange={() => toggleSelection(item.id)}
                          />
                          <span>选择</span>
                        </label>
                        <div className="vocabulary-card-title">
                          <span className={`vocabulary-status ${item.status}`}>{STATUS_LABELS[item.status]}</span>
                          <span className={`vocabulary-export-mark ${item.exported_before ? "exported" : "new"}`}>
                            {item.exported_before ? "已导出" : "未导出"}
                          </span>
                          {distinctArticles >= 2 ? (
                            <span className="vocabulary-frequency-reminder">
                              高频复现 · {distinctArticles} 篇文章，建议优先记忆
                            </span>
                          ) : null}
                          {item.manual_capture_count >= 2 ? (
                            <span className="vocabulary-frequency-reminder">
                              手动高频 · 已记录 {item.manual_capture_count} 次
                            </span>
                          ) : null}
                          <h2>{item.term}</h2>
                          <small>
                            出现 {item.occurrence_count} 次 · {item.sources.length} 个来源
                            {item.manual_capture_count ? ` · 手动记录 ${item.manual_capture_count} 次` : ""}
                          </small>
                        </div>
                        <div className="vocabulary-card-actions">
                          <button className="secondary-button" type="button" onClick={() => beginEdit(item)}>编辑</button>
                          <button className="vocabulary-delete-button" type="button" onClick={() => void removeItem(item)}>删除</button>
                        </div>
                      </div>

                      {isEditing && editing ? (
                        <div className="vocabulary-edit-form">
                          <label><span>中文释义</span><textarea rows={3} value={editing.meaning} onChange={(event) => setEditing({ ...editing, meaning: event.target.value })} /></label>
                          <label><span>个人笔记</span><textarea rows={3} value={editing.note} onChange={(event) => setEditing({ ...editing, note: event.target.value })} /></label>
                          <label><span>状态</span><select value={editing.status} onChange={(event) => setEditing({ ...editing, status: event.target.value as EditState["status"] })}><option value="learning">学习中</option><option value="mastered">已掌握</option></select></label>
                          <div><button className="primary-button" type="button" onClick={() => void saveEdit()} disabled={saving}>保存修改</button><button className="secondary-button" type="button" onClick={() => setEditing(null)}>取消</button></div>
                        </div>
                      ) : (
                        <>
                          <div className="vocabulary-content-grid">
                            <div><span>中文释义</span><p>{item.meaning || "尚未填写"}</p></div>
                            <div><span>个人笔记</span><p>{item.note || "尚未填写"}</p></div>
                          </div>
                          <div className="vocabulary-sources">
                            <strong>来源记录</strong>
                            {item.sources.slice(0, 4).map((source) => (
                              <div key={source.id}>
                                <span>{SOURCE_LABELS[source.source_type] || source.source_type}</span>
                                <p>{source.source_sentence || source.source_context || "手动添加"}</p>
                                <small>{[source.test_title, source.part_number ? `Part ${source.part_number}` : ""].filter(Boolean).join(" · ") || "个人词汇本"}</small>
                              </div>
                            ))}
                            {item.sources.length > 4 ? <small>另有 {item.sources.length - 4} 条来源，导出文件中会完整保留。</small> : null}
                          </div>
                        </>
                      )}
                    </article>
                  );
                })}
              </div>
            ) : <div className="vocabulary-empty">还没有符合条件的词汇。先在左侧添加一个单词或词组。</div>
          ) : (
            loading ? <div className="vocabulary-loading">正在读取同义替换…</div> : visibleParaphrases.length ? (
              <div className="vocabulary-list">
                {visibleParaphrases.map((item) => {
                  const distinctArticles = paraphraseArticleCount(item);
                  return (
                    <article className="vocabulary-card paraphrase-card" key={item.id}>
                      <div className="vocabulary-card-heading">
                        <label className="vocabulary-card-select">
                          <input
                            type="checkbox"
                            checked={selectedParaphraseIds.has(item.id)}
                            onChange={() => toggleParaphraseSelection(item.id)}
                          />
                          <span>选择</span>
                        </label>
                        <div className="vocabulary-card-title">
                          <span className={`vocabulary-status ${item.status}`}>{STATUS_LABELS[item.status]}</span>
                          <span className={`vocabulary-export-mark ${item.exported_before ? "exported" : "new"}`}>
                            {item.exported_before ? "已导出" : "未导出"}
                          </span>
                          {distinctArticles >= 2 ? (
                            <span className="vocabulary-frequency-reminder">
                              高频错题点 · {distinctArticles} 篇文章反复出现
                            </span>
                          ) : null}
                          <h2><span>{item.question_phrase}</span><b>=</b><span>{item.source_phrase}</span></h2>
                          <small>
                            错题来源 {item.occurrence_count} 次 · {
                              PARAPHRASE_RELATION_LABELS[item.relation_type]
                            } {Math.round(item.confidence * 100)}%
                          </small>
                        </div>
                        <div className="vocabulary-card-actions">
                          {item.status === "learning" ? (
                            <button className="secondary-button" type="button" onClick={() => void markParaphraseStatus(item, "mastered")} disabled={saving}>标为掌握</button>
                          ) : (
                            <button className="secondary-button" type="button" onClick={() => void markParaphraseStatus(item, "learning")} disabled={saving}>继续学习</button>
                          )}
                        </div>
                      </div>
                      <div className="vocabulary-content-grid">
                        <div><span>题目表达</span><p>{item.question_phrase}</p></div>
                        <div><span>原文表达</span><p>{item.source_phrase}</p></div>
                      </div>
                      {item.note ? <p className="paraphrase-note">{item.note}</p> : null}
                      <div className="vocabulary-sources">
                        <strong>错题来源</strong>
                        {item.sources.slice(0, 4).map((source) => (
                          <div key={source.id}>
                            <span>{[source.test_title, source.part_number ? `Part ${source.part_number}` : "", source.question_number ? `Q${source.question_number}` : ""].filter(Boolean).join(" · ")}</span>
                            <p>{source.question_prompt || "题目内容未记录"}</p>
                            {source.evidence ? (
                              <blockquote className="paraphrase-evidence">
                                <b>原文证据</b>
                                {source.evidence}
                              </blockquote>
                            ) : null}
                            <small>你的答案：{source.user_answer || "空"} · 正确答案：{source.correct_answer || "—"}</small>
                          </div>
                        ))}
                        {item.sources.length > 4 ? <small>另有 {item.sources.length - 4} 条错题来源。</small> : null}
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : <div className="vocabulary-empty">还没有错题同义替换。完成带错题的练习后，系统会自动尝试记录。</div>
          )}
        </div>
      </section>
    </div>
  );
}
