"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  fetchAiProviderStatus,
  fetchQuestionBankStatus,
  fetchTests,
  selectAiProvider,
  type AiProviderStatus,
  type QuestionBankMigrationStatus
} from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "学习总览", icon: "home" },
  { href: "/practice", label: "题库与考试", icon: "screen" },
  { href: "/history", label: "练习记录", icon: "history" },
  { href: "/review", label: "错题复盘", icon: "review" },
  { href: "/reports", label: "阶段报告", icon: "report" },
  { href: "/methods", label: "方法课程", icon: "book" },
  { href: "/ability", label: "专项训练", icon: "grid" },
  { href: "/plan", label: "学习计划", icon: "calendar" },
  { href: "/sentences", label: "长难句", icon: "sentence" },
  { href: "/vocabulary", label: "生词本", icon: "vocabulary" },
  { href: "/teacher", label: "老师作业", icon: "teacher" },
  { href: "/diagnosis", label: "学习诊断", icon: "diagnosis" },
  { href: "/support", label: "设置与帮助", icon: "settings" }
] as const;

function NavIcon({ name }: { name: (typeof NAV_ITEMS)[number]["icon"] }) {
  const paths: Record<typeof name, ReactNode> = {
    home: <><path d="m3 11 9-8 9 8" /><path d="M5 10v10h14V10M9 20v-6h6v6" /></>,
    screen: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8m-4-4v4" /></>,
    review: <><path d="M5 4h14v16H5zM8 8h8m-8 4h5" /><path d="m15 16 1.5 1.5L20 14" /></>,
    report: <><path d="M5 3h11l3 3v15H5z" /><path d="M9 16v-3m3 3V9m3 7v-5" /></>,
    book: <><path d="M4 5.5A3.5 3.5 0 0 1 7.5 2H12v17H7.5A3.5 3.5 0 0 0 4 22z" /><path d="M20 5.5A3.5 3.5 0 0 0 16.5 2H12v17h4.5A3.5 3.5 0 0 1 20 22z" /></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M8 3v4m8-4v4M3 10h18m-13 4h3m2 0h3m-8 3h3" /></>,
    sentence: <><path d="M5 4h14M5 9h10M5 14h14M5 19h8" /><path d="m17 17 2 2 3-4" /></>,
    vocabulary: <><path d="M5 3h12a2 2 0 0 1 2 2v16H7a2 2 0 0 1-2-2z" /><path d="M8 7h8M8 11h6M5 18a3 3 0 0 1 3-3h11" /></>,
    history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2M3 5v5h5" /></>,
    teacher: <><circle cx="9" cy="8" r="3" /><path d="M3 20c0-4 2-6 6-6s6 2 6 6M15 5h6v9h-4" /></>,
    diagnosis: <><path d="M4 19V9m5 10V5m5 14v-7m5 7V3" /><path d="M2 21h20" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.3 1A7 7 0 0 0 15 6l-.3-2.5h-4L10.4 6a7 7 0 0 0-1.7 1.1l-2.3-1-2 3.4L6.1 11a7 7 0 0 0 0 2l-1.8 1.5 2 3.4 2.3-1A7 7 0 0 0 10.4 18l.3 2.5h4L15 18a7 7 0 0 0 1.7-1.1l2.3 1 2-3.4-2-1.5a7 7 0 0 0 .1-1z" /></>
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24">{paths[name]}</svg>;
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [providerStatus, setProviderStatus] = useState<AiProviderStatus | null>(null);
  const [providerDialogOpen, setProviderDialogOpen] = useState(false);
  const [providerSaving, setProviderSaving] = useState("");
  const [providerError, setProviderError] = useState("");
  const [libraryStats, setLibraryStats] = useState<{ tests: number; parts: number; questions: number } | null>(null);
  const [libraryStatus, setLibraryStatus] = useState<QuestionBankMigrationStatus | null>(null);
  const activeItem = NAV_ITEMS.find((item) => item.href === "/" ? pathname === "/" : pathname.startsWith(item.href));

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchAiProviderStatus(controller.signal)
      .then(setProviderStatus)
      .catch(() => setProviderStatus(null));
    void fetchTests(controller.signal)
      .then((tests) => setLibraryStats({
        tests: tests.length,
        parts: tests.reduce((total, test) => total + Number(test.part_count || 0), 0),
        questions: tests.reduce((total, test) => total + Number(test.question_count || 0), 0)
      }))
      .catch(() => setLibraryStats(null));
    void fetchQuestionBankStatus(controller.signal)
      .then(setLibraryStatus)
      .catch(() => setLibraryStatus(null));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!providerDialogOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProviderDialogOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [providerDialogOpen]);

  async function chooseProvider(provider: string) {
    setProviderSaving(provider);
    setProviderError("");
    try {
      const nextStatus = await selectAiProvider(provider);
      setProviderStatus(nextStatus);
      window.dispatchEvent(new CustomEvent("ielts-ai-provider-changed", { detail: nextStatus }));
    } catch (error) {
      setProviderError(error instanceof Error ? error.message : "切换失败，请稍后重试。");
    } finally {
      setProviderSaving("");
    }
  }

  return (
    <div className="app-shell">
      <aside className={mobileMenuOpen ? "sidebar mobile-open" : "sidebar"} aria-label="主导航">
        <Link className="brand" href="/">
          <span className="brand-mark" aria-hidden="true"><NavIcon name="book" /></span>
          <span><strong>IELTS G类阅读</strong><small>AI 教练版 <b>V1.0</b></small></span>
        </Link>
        <button
          type="button"
          className="mobile-menu-button"
          aria-expanded={mobileMenuOpen}
          aria-controls="primary-navigation"
          aria-label={mobileMenuOpen ? "关闭菜单" : "打开菜单"}
          onClick={() => setMobileMenuOpen((open) => !open)}
        >
          <span /><span /><span />
        </button>
        <nav className="nav-list" id="primary-navigation">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={active ? "nav-item active" : "nav-item"} aria-current={active ? "page" : undefined}>
                <NavIcon name={item.icon} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className={libraryStatus && !libraryStatus.ready ? "library-ready incomplete" : "library-ready"}>
            <span />
            {libraryStatus
              ? `${libraryStatus.found_tests}/${libraryStatus.expected_tests}套题库已安装`
              : libraryStats
                ? `${libraryStats.tests}套题库可用`
                : "正在核对题库"}
            <strong>
              {libraryStatus && !libraryStatus.ready
                ? `缺少${libraryStatus.missing_test_ids.length}套私有题库，请先完成安装校验`
                : libraryStats
                  ? `${libraryStats.parts} Parts · ${libraryStats.questions.toLocaleString("zh-CN")}题`
                  : "由后端校验可用内容"}
            </strong>
          </div>
          <p>个人本地学习空间</p>
        </div>
      </aside>
      <div className="page-column">
        <header className="app-topbar">
          <div>
            <span className="topbar-dot" />
            <strong>{activeItem?.label || "IELTS G类阅读"}</strong>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              className={providerStatus?.configured ? "ai-status-chip ready" : "ai-status-chip"}
              onClick={() => setProviderDialogOpen(true)}
              aria-haspopup="dialog"
            >
              <span />{providerStatus ? `${providerStatus.selected_label} · ${providerStatus.model}` : "AI 老师"}⌄
            </button>
            <div className="learner-chip"><span>G</span><strong>学习者</strong></div>
          </div>
        </header>
        <main className="page-stage">{children}</main>
      </div>
      {providerDialogOpen && (
        <div className="system-modal-backdrop provider-modal-backdrop" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setProviderDialogOpen(false);
        }}>
          <section className="system-modal provider-selector-modal" role="dialog" aria-modal="true" aria-labelledby="provider-dialog-title">
            <header>
              <div>
                <p className="eyebrow">AI TEACHER</p>
                <h2 id="provider-dialog-title">选择 AI 老师模型</h2>
                <p>教学报告和逐题 AI 讲解会使用当前选择；切换本身不会调用模型，也不会产生费用。</p>
              </div>
              <button type="button" onClick={() => setProviderDialogOpen(false)} aria-label="关闭">×</button>
            </header>
            <div className="provider-option-list">
              {(providerStatus?.providers || []).map((provider) => {
                const selected = provider.id === providerStatus?.selected;
                return (
                  <button
                    type="button"
                    className={selected ? "provider-option selected" : "provider-option"}
                    key={provider.id}
                    disabled={Boolean(providerSaving)}
                    onClick={() => void chooseProvider(provider.id)}
                  >
                    <span><strong>{provider.label}</strong><small>{provider.model}</small></span>
                    <em>{providerSaving === provider.id ? "正在切换" : selected ? "当前使用" : provider.configured ? "可选择" : "未配置"}</em>
                  </button>
                );
              })}
            </div>
            {providerError && <p className="page-error">{providerError}</p>}
            <footer>
              <p>未配置的模型可先选择，但调用讲解前需要在项目 <code>.env</code> 中填写对应 API Key 并重启应用。</p>
              <Link href="/diagnosis" onClick={() => setProviderDialogOpen(false)}>进入学习诊断 →</Link>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}
