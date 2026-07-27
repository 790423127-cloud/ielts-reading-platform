import Link from "next/link";
import DashboardLearningStatus from "@/components/DashboardLearningStatus";

const CURRENT_VERSION = "0.5.0";

const LEARNING_ENTRIES = [
  {
    href: "/practice",
    tone: "mint",
    icon: "▣",
    title: "模拟考试模式",
    body: "英文机考界面、60 分钟倒计时、高亮和笔记；交卷前不显示答案。",
    action: "选择套题"
  },
  {
    href: "/practice",
    tone: "blue",
    icon: "▤",
    title: "学习中心",
    body: "可练单个 Part，也可整套学习；保留答题进度与文章上下文。",
    action: "选择学习方式"
  },
  {
    href: "/ability",
    tone: "violet",
    icon: "⌘",
    title: "按题型专项练习",
    body: "填空、单选、匹配、判断等 17 种具体题型，全部使用真实题。",
    action: "选择题型"
  },
  {
    href: "/review",
    tone: "amber",
    icon: "✦",
    title: "练习我的错题",
    body: "保留原文章、原题组和定位证据，可单题复盘或批量再练。",
    action: "开始错题训练"
  },
  {
    href: "/teacher",
    tone: "rose",
    icon: "♟",
    title: "真人老师作业",
    body: "把多套 Part、多个题型和多天任务组织为同一份作业。",
    action: "进入作业中心"
  },
  {
    href: "/teacher#report-history",
    tone: "sky",
    icon: "▥",
    title: "教师报告历史",
    body: "查看阶段报告和作业批次快照；报告只使用真实已保存记录。",
    action: "进入报告中心"
  }
] as const;

export default function DashboardPage() {
  return (
    <section className="page-wrap dashboard-page">
      <DashboardLearningStatus version={CURRENT_VERSION} statusLabel="旧版替代仍在验收 · 新旧优势合并">
        <section className="dashboard-stat-grid" aria-label="题库概览">
          <article><span>完整套题</span><strong>58</strong><small>剑雅 4–21</small></article>
          <article><span>阅读 Part</span><strong>174</strong><small>可单独训练</small></article>
          <article><span>真实题目</span><strong>2,320</strong><small>服务端判分</small></article>
          <article><span>方法课程</span><strong>22</strong><small>5基础 + 17题型</small></article>
        </section>

        <section className="dashboard-section">
          <div className="dashboard-section-heading">
            <div><p className="eyebrow">LEARNING ENTRANCE</p><h2>选择今天的学习入口</h2></div>
            <p>完整保留旧版更清楚的做题方式，同时沿用新版真实题库与判分链路。</p>
          </div>
          <div className="learning-entry-grid">
            {LEARNING_ENTRIES.map((item, index) => (
              <Link className={`learning-entry-card ${item.tone}`} href={item.href} key={`${item.href}-${index}`}>
                <div><span className="entry-icon">{item.icon}</span><span className="entry-arrow">→</span></div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <strong>{item.action}</strong>
              </Link>
            ))}
          </div>
        </section>

        <section className="learning-flow-card">
          <div>
            <p className="eyebrow">YOUR LEARNING LOOP</p>
            <h2>一条完整的阅读学习路径</h2>
            <p>方法课、学习计划与阶段报告是新版保留的增强入口，不挤占旧版六种核心做题方式。</p>
            <div className="learning-flow-links">
              <Link href="/methods">做题方法课</Link>
              <Link href="/plan">学习计划</Link>
              <Link href="/reports">阶段报告</Link>
            </div>
          </div>
          <ol>
            <li><span>1</span><strong>完成真实题</strong><small>模考或专项训练</small></li>
            <li><span>2</span><strong>查看错题证据</strong><small>定位与答案对照</small></li>
            <li><span>3</span><strong>学习对应方法</strong><small>修正具体步骤</small></li>
            <li><span>4</span><strong>再次验证</strong><small>用新题检查掌握</small></li>
          </ol>
        </section>
      </DashboardLearningStatus>
    </section>
  );
}
