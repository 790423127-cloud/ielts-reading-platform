# IELTS Reading Platform

IELTS General Training Reading 个人学习平台。

本仓库采用渐进迁移：保留旧版 `ielts-g-reading-ai-coach` 作为业务基线，不复制其历史前端路由、版本补丁和 DOM 观察器；在这里使用 Next.js + React + TypeScript 重建前端，继续使用 FastAPI 承载题库、Session、确定性判分、Band、学习计划、能力训练和 AI 安全边界。

## 当前结构

- `apps/web`：Next.js 产品前端；
- `services/api`：FastAPI 业务后端；
- `packages/contracts`：前后端共享的数据协议；
- `docs`：架构、迁移和旧新对照标准。

## 已完成能力

- 46套 GT Reading 真实题库与确定性判分；
- 完整模考、单 Part 训练、Session 历史和错题解析；
- 错题复盘、22门方法课和七种真实题能力训练；
- 后台学习计划、跨日期掌握规则与第3天复习；
- 审核长难句五步训练与个人句子拆解；
- 词汇本、来源去重以及 CSV/TXT/JSON 导出；
- 错题、长难句和学习计划的证据约束 AI 学习老师；
- AI 对话历史、自动摘要、相同问题缓存、每日调用上限和 token 审计。

当前个人学习产品范围已经推进到词汇本导出和 AI 学习辅助。订阅、支付、套餐、语音和其他商业化功能暂缓。

## 迁移原则

1. 标准答案、确定性判分和完整 40 题 Band 规则只能由后端决定。
2. 模考进行中后端拒绝 AI 教学帮助。
3. 未提交练习不返回答案或解析。
4. 每项迁移必须通过旧新结果对照测试后才能取代旧版。
5. 不迁移旧 `v311-router.js`、`v320-nav-guard.js`、版本补丁 CSS 或模块内 hash 监听。
6. 当前旧站继续可用；新站达到功能对等后再切换。
7. 新系统从第一天支持 `user_id` 数据归属；个人管理员账号可以保持无限额度。
8. AI 只能解释服务端提供的学习证据，不能修改答案、成绩、Band、任务状态或掌握度。

## AI 学习老师配置

AI 功能使用服务端环境变量，不把密钥写入前端或仓库：

```bash
export OPENAI_API_KEY="你的服务端密钥"
export OPENAI_MODEL="gpt-5-mini"
export AI_DAILY_REQUEST_LIMIT="30"
```

- 没有配置 `OPENAI_API_KEY` 时，题库、判分、学习计划、长难句和词汇本仍可正常使用，AI 面板会显示明确的未配置提示；
- `AI_DAILY_REQUEST_LIMIT` 只限制当天新增的真实 AI 调用，相同问题命中缓存时不会增加调用；
- 自动测试使用模拟提供方，不会调用真实付费接口；
- Responses API 请求设置 `store=False`，系统本地只保存学习对话、模型名、请求 ID 和 token 用量。

## 本地开发

```bash
corepack enable
pnpm install
pnpm dev:web
```

另一个终端：

```bash
python -m venv .venv
pip install -e "services/api[dev]"
uvicorn app.main:app --reload --app-dir services/api --port 8000
```

详细路线见 `docs/MIGRATION.md`，架构约束见 `docs/ARCHITECTURE.md`。
