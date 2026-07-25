# IELTS Reading Platform

IELTS General Training Reading 商业化重建仓库。

本仓库采用渐进迁移：保留旧版 `ielts-g-reading-ai-coach` 作为业务基线，不复制其历史前端路由、版本补丁和 DOM 观察器；在这里使用 Next.js + React + TypeScript 重建前端，继续使用 FastAPI 承载题库、Session、确定性判分、Band、学习计划、能力训练和 AI 安全边界。

## 迁移原则

1. 标准答案、确定性判分和完整 40 题 Band 规则只能由后端决定。
2. 模考进行中后端拒绝 AI 教学帮助。
3. 未提交练习不返回答案或解析。
4. 每项迁移必须通过旧新结果对照测试后才能取代旧版。
5. 不迁移旧 `v311-router.js`、`v320-nav-guard.js`、版本补丁 CSS 或模块内 hash 监听。
6. 当前旧站继续可用；新站达到功能对等后再切换。

详细路线见 `docs/MIGRATION.md`（将在首个架构 PR 中加入）。
