# IELTS Reading Platform

IELTS General Training Reading 个人学习平台。

本仓库采用渐进迁移：保留旧版 `ielts-g-reading-ai-coach` 作为业务基线，不复制其历史前端路由、版本补丁和 DOM 观察器；在这里使用 Next.js + React + TypeScript 重建前端，继续使用 FastAPI 承载题库、Session、确定性判分、Band、学习计划、能力训练和 AI 安全边界。

## 当前结构

- `apps/web`：Next.js 产品前端；
- `services/api`：FastAPI 业务后端；
- `packages/contracts`：共享数据协议定义；Web 尚未由编译器强制复用该包；
- `docs`：架构、迁移和旧新对照标准。

## 当前发布状态

- 当前版本：`0.5.0`；
- 当前阶段：`replacement_validation`（旧版替代验收）；
- 个人学习主线已经完成到词汇本导出和证据约束 AI；
- 17种题型专项、返回原错题和确定性阶段报告已经迁入，并与现有能力训练、Session 和错题闭环合并；
- 教师可编辑作业、独立 DOCX 报告和可恢复批量 AI 任务仍需数据库结构与费用边界决策；
- 真实浏览器、移动端、性能以及正式数据迁移切换尚未完成最终验收；
- 在上述项目完成前，旧系统继续作为功能基线和回退系统。

## 已完成能力

- 58套 GT Reading 真实题库（剑雅4–21）与确定性判分；
- 完整模考、单 Part 训练、Session 历史和错题解析；
- 错题复盘、原题精确重做、22门方法课、七种能力训练和17种题型专项；
- 基于已保存 Session 的阶段学习报告，可由浏览器打印或保存 PDF；
- 后台学习计划、跨日期掌握规则与第3天复习；
- 审核长难句五步训练与个人句子拆解；
- 词汇本、来源去重以及 CSV/TXT/JSON 导出；
- 错题、长难句和学习计划的证据约束 AI 学习老师；
- AI 对话历史、自动摘要、相同问题缓存、每日调用上限和 token 审计；
- 千问、DeepSeek 和 OpenAI 服务端供应商适配。
- 默认只预览、显式应用、自动备份并可按清单回退的旧学习数据迁移工具。

## 旧学习记录迁移

先做只读预览，不会写入新版数据库：

```powershell
python scripts/migrate_legacy_learning_data.py `
  --source-db "旧版\data\progress.db" `
  --destination-db "services\api\data\sessions.sqlite3"
```

只有核对预览数量后才使用 `--apply`。工具会在目标数据库已经存在时先创建时间戳备份，并输出记录本次新增 Session 的迁移清单。回退也默认只预览；必须同时提供 `--rollback-manifest` 和 `--apply` 才会删除该清单新增的记录。

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

新系统兼容旧系统的变量名称。复制示例文件后，只填写你实际使用的供应商，不要把密钥提交到 GitHub：

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
```

### 千问

```env
AI_PROVIDER=qwen
DASHSCOPE_API_KEY=你的阿里云百炼_API_Key
QWEN_MODEL=qwen3.7-plus
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_DAILY_REQUEST_LIMIT=30
```

### DeepSeek

```env
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的_DeepSeek_API_Key
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
AI_DAILY_REQUEST_LIMIT=30
```

### OpenAI（可选）

```env
AI_PROVIDER=openai
OPENAI_API_KEY=你的服务端密钥
OPENAI_MODEL=gpt-5-mini
AI_DAILY_REQUEST_LIMIT=30
```

- 本地后端会读取仓库根目录或 `services/api` 目录下的 `.env`；已有系统环境变量优先，不会被文件覆盖；
- 选中的供应商没有配置密钥时会明确报错，不会偷偷改用另一家付费模型；
- 千问和 DeepSeek 通过各自的 OpenAI 兼容 Chat Completions 接口调用；OpenAI 继续使用 Responses API；
- `AI_DAILY_REQUEST_LIMIT` 只限制当天新增的真实 AI 调用，相同问题命中缓存时不会增加调用；
- 自动测试使用模拟提供方，不会调用真实付费接口；
- 可访问 `GET /api/v1/ai-teacher/provider` 检查当前供应商、模型和配置状态，接口不会返回 API Key。

## 本地开发

```bash
corepack enable
pnpm install
pnpm dev:web
```

新版界面固定使用 `http://127.0.0.1:8001`。

另一个终端：

```bash
python -m venv .venv
pip install -e "services/api[dev]"
uvicorn app.main:app --reload --app-dir services/api --port 8010
```

新版内部 API 固定使用 `8010`；旧版 `8000` 不受影响。

详细路线见 `docs/MIGRATION.md`，架构约束见 `docs/ARCHITECTURE.md`。
