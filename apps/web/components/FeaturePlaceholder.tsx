import Link from "next/link";

export default function FeaturePlaceholder({ title, description, phase }: { title: string; description: string; phase: string }) {
  return (
    <section className="page-wrap">
      <header className="page-heading"><p className="eyebrow">MIGRATION {phase}</p><h1>{title}</h1><p>{description}</p></header>
      <article className="placeholder-card">
        <div className="placeholder-icon" aria-hidden="true">↗</div>
        <div><h2>该模块将从旧系统做结果对照迁移</h2><p>不会复制旧路由、版本补丁或 DOM 观察器。后端规则通过一致性测试后，才会接入此页面。</p></div>
      </article>
      <Link className="secondary-link" href="/">返回迁移总览</Link>
    </section>
  );
}
