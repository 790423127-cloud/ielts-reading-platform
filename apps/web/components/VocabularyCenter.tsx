"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  captureVocabulary,
  deleteVocabulary,
  fetchVocabulary,
  updateVocabulary,
  vocabularyExportUrl,
  type VocabularyItem
} from "@/lib/learningApi";

const STATUS_LABELS = {
  learning: "学习中",
  mastered: "已掌握"
} as const;

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

export default function VocabularyCenter() {
  const [items, setItems] = useState<VocabularyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "learning" | "mastered">("all");
  const [editing, setEditing] = useState<EditState | null>(null);
  const [draft, setDraft] = useState({
    term: "",
    meaning: "",
    note: "",
    source_sentence: ""
  });

  useEffect(() => {
    const controller = new AbortController();
    fetchVocabulary("owner", controller.signal)
      .then(setItems)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "词汇本读取失败");
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

  const learningCount = items.filter((item) => item.status === "learning").length;
  const masteredCount = items.length - learningCount;
  const occurrenceCount = items.reduce((total, item) => total + item.occurrence_count, 0);

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

  async function removeItem(item: VocabularyItem) {
    if (!window.confirm(`确定删除“${item.term}”吗？此操作会同时删除它的来源记录。`)) return;
    setSaving(true);
    setError("");
    try {
      await deleteVocabulary(item.id);
      setItems((current) => current.filter((row) => row.id !== item.id));
      if (editing?.id === item.id) setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除词汇失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-wrap vocabulary-page">
      <header className="page-heading vocabulary-heading">
        <div>
          <p className="eyebrow">PERSONAL VOCABULARY</p>
          <h1>我的词汇本</h1>
          <p>同一个词会自动合并，不同原句和来源继续保留。CSV 可直接用 Excel 打开，JSON 用于完整备份。</p>
        </div>
        <div className="vocabulary-export-actions">
          <a className="primary-button" href={vocabularyExportUrl("csv")}>导出 CSV</a>
          <a className="secondary-button" href={vocabularyExportUrl("txt")}>导出 TXT</a>
          <a className="secondary-button" href={vocabularyExportUrl("json")}>备份 JSON</a>
        </div>
      </header>

      {error ? <div className="page-error vocabulary-error">{error}</div> : null}

      <section className="vocabulary-stat-strip">
        <article><span>词汇总数</span><strong>{items.length}</strong></article>
        <article><span>学习中</span><strong>{learningCount}</strong></article>
        <article><span>已掌握</span><strong>{masteredCount}</strong></article>
        <article><span>累计来源</span><strong>{occurrenceCount}</strong></article>
      </section>

      <section className="vocabulary-layout">
        <form className="vocabulary-capture-card" onSubmit={submitNewItem}>
          <div className="section-title-row">
            <div><span>QUICK CAPTURE</span><h2>添加词汇</h2></div>
          </div>
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
          <p className="vocabulary-dedupe-note">重复收藏不会覆盖已有释义和笔记；新的原句会追加为新来源。</p>
        </form>

        <div className="vocabulary-library">
          <div className="vocabulary-toolbar">
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索单词、释义或笔记" />
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
              <option value="all">全部状态</option>
              <option value="learning">学习中</option>
              <option value="mastered">已掌握</option>
            </select>
            <span>显示 {visibleItems.length}/{items.length}</span>
          </div>

          {loading ? <div className="vocabulary-loading">正在读取词汇本…</div> : visibleItems.length ? (
            <div className="vocabulary-list">
              {visibleItems.map((item) => {
                const isEditing = editing?.id === item.id;
                return (
                  <article className="vocabulary-card" key={item.id}>
                    <div className="vocabulary-card-heading">
                      <div>
                        <span className={`vocabulary-status ${item.status}`}>{STATUS_LABELS[item.status]}</span>
                        <h2>{item.term}</h2>
                        <small>出现 {item.occurrence_count} 次 · {item.sources.length} 个来源</small>
                      </div>
                      <div className="vocabulary-card-actions">
                        <button className="secondary-button" type="button" onClick={() => beginEdit(item)}>编辑</button>
                        <button className="vocabulary-delete-button" type="button" onClick={() => removeItem(item)}>删除</button>
                      </div>
                    </div>

                    {isEditing && editing ? (
                      <div className="vocabulary-edit-form">
                        <label><span>中文释义</span><textarea rows={3} value={editing.meaning} onChange={(event) => setEditing({ ...editing, meaning: event.target.value })} /></label>
                        <label><span>个人笔记</span><textarea rows={3} value={editing.note} onChange={(event) => setEditing({ ...editing, note: event.target.value })} /></label>
                        <label><span>状态</span><select value={editing.status} onChange={(event) => setEditing({ ...editing, status: event.target.value as EditState["status"] })}><option value="learning">学习中</option><option value="mastered">已掌握</option></select></label>
                        <div><button className="primary-button" type="button" onClick={saveEdit} disabled={saving}>保存修改</button><button className="secondary-button" type="button" onClick={() => setEditing(null)}>取消</button></div>
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
          ) : <div className="vocabulary-empty">还没有符合条件的词汇。先在左侧添加一个单词或词组。</div>}
        </div>
      </section>
    </div>
  );
}
