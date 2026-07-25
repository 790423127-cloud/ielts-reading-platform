const MILESTONES = [
  { title: "平台骨架", status: "进行中", body: "Next.js、FastAPI、共享契约和 CI。" },
  { title: "判分与 Session", status: "下一步", body: "迁移题库读取、答案隔离、确定性判分和 40 题 Band。" },
  { title: "考试工作台", status: "待迁移", body: "Part、整套模考、计时、草稿恢复和幂等提交。" },
  { title: "学习闭环", status: "待迁移", body: "错题、17种题型、7种能力、方法课与返回原题。" },
  { title: "计划与句子", status: "待迁移", body: "掌握度、到期复习、固定句与我的句子。" },
  { title: "AI与词汇", status: "最后", body: "自由文字老师和词汇摘录在稳定架构上开发。" }
];

export default function DashboardPage() {
  return (
    <section className="page-wrap">
      <header className="hero">
        <div><p className="eyebrow">IELTS GENERAL TRAINING READING</p><h1>先保证学习规则一致，<br />再重做商业产品体验。</h1><p>旧版继续提供可用基线；新版只迁移经过验证的题库、判分、Session和教学资产。</p></div>
        <div className="hero-card"><span>当前阶段</span><strong>0.1</strong><p>平台骨架与迁移边界</p></div>
      </header>
      <div className="milestone-grid">
        {MILESTONES.map((item, index) => <article key={item.title} className="milestone-card"><span>{String(index + 1).padStart(2, "0")}</span><div><small>{item.status}</small><h2>{item.title}</h2><p>{item.body}</p></div></article>)}
      </div>
      <section className="guardrails"><h2>不可破坏的边界</h2><div><p>提交前不返回答案或解析</p><p>AI不能修改答案与判分</p><p>只有完整40题显示Band</p><p>模考进行中后端拒绝AI</p></div></section>
    </section>
  );
}
