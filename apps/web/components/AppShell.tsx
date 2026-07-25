"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "/", label: "学习总览" },
  { href: "/practice", label: "题库与考试" },
  { href: "/review", label: "错题复盘" },
  { href: "/methods", label: "做题方法" },
  { href: "/ability", label: "能力训练" },
  { href: "/plan", label: "学习计划" },
  { href: "/sentences", label: "长难句" }
] as const;

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <Link className="brand" href="/">
          <span className="brand-mark">R</span>
          <span><strong>IELTS Reading</strong><small>新平台迁移版</small></span>
        </Link>
        <nav className="nav-list">
          {NAV_ITEMS.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={active ? "nav-item active" : "nav-item"} aria-current={active ? "page" : undefined}>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="migration-badge"><span />46套题库已迁移<br />真实判分对照保持全绿</div>
      </aside>
      <main className="page-stage">{children}</main>
    </div>
  );
}
