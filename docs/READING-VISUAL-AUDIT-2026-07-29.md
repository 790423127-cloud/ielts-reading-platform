# 剑雅 G 类阅读 4–21 桌面端全量视觉与答题审计

审计日期：2026-07-29
修改范围：仅新版 `C:\Users\Administrator\Desktop\ai教练新版\雅思阅读新版`
主要视觉基准：本机“雅思哥机考软件”G 类阅读
补充视觉基准：爱听写 `https://www.idictation.cn/`
题库范围：剑雅 4–21，共 58 套、174 个 Part、2,320 题

## 1. 结论

本轮没有用剑雅 5 或任何单篇文章代表全题库。

新版 58 套题的 174 个 Part 已逐个打开，每个 Part 均重新生成顶部、中部、底部三张桌面截图，共 522 张；又按剑雅 4–21 生成 18 张全书联系表并逐张目视检查。当前题库实际出现的 16 类题型也逐类完成了真实点击、选择、输入和状态验证。

第二轮全量渲染结果：

```text
58 tests
174 Parts
522 screenshots
pageErrors: 0
layout/content anomalies: 0
```

当前未发现仍阻断桌面阅读或作答的 P0/P1 问题。

## 2. 实际对照方式

### 2.1 系统 Chrome 实际操作

已在系统 Chrome 中实际打开新版 `http://127.0.0.1:8001/practice`，并操作、截图核验：

- 剑雅 5 Test A Part 2：`WORK & TRAVEL USA` 广告、J-1、电话号码、粗体品牌、题目矩阵；
- 剑雅 17 Test 1 Part 3：A/B/C/D 分段字母、段落标题匹配、笔记填空和单选；
- 文章和题目独立滚动；
- 左右分栏、拖动分隔线和底部题号栏；
- 普通高亮、取消高亮和手动草稿状态。

系统 Chrome 的实际 DOM 同时确认了题干、选项、表格和所有可访问答题控件，不只依靠截图判断。

### 2.2 雅思哥本机缓存逐字交叉核对

从本机雅思哥缓存中读取到剑雅 17、19、20 的真实 `passagesContent`，逐段对照新版数据。确认并修复：

- 剑雅 17 矿井安全文章的 A/B/C/D/E 字母应与首段正文同一行；
- `1815.The`、`1816.However` 等句号后缺空格；
- 剑雅 19 公交文章被 OCR 错误拆开的 `first` / `city bus service.`；
- 剑雅 19 领导力文章被拆开的 `design of` / `a new strategy.`；
- 剑雅 20 困难谈话文章中同属一个段落的提示句和 `First, ...`；
- `'them and us'culture`、`paragraph-the` 等粘连；
- 雅思哥原始缓存自身仍有少量 `lf`/`lt` OCR 错字时，保留新版已经确认正确的 `If`/`It`，不把错误复制回来。

### 2.3 新版全题库逐页验收

自动化脚本不是抽样：它依次进入全部 58 套的全部 174 个 Part，并检查：

- 所有应出现的题号和答题控件存在；
- 页面、文章区、题目区无横向溢出；
- 无残留未渲染的 `_____` 模板；
- 文章默认字号、字重、行距一致；
- 题干、说明、选项和输入框字号一致；
- 8px 可拖动分隔线与 40px 底部题号栏存在；
- 字母匹配矩阵的真实选项列、行高和换行正确；
- 描述型匹配可根据题目栏宽度上下重排；
- 原文表格字体不小于 15px；
- A/B/C 分段字母无卡片框、无底色，并与正文内联；
- 浏览器页面脚本无运行异常。

截图和指标输出位于：

- `output/reading-visual-audit-2026-07-29/parts`
- `output/reading-visual-audit-2026-07-29/contact-sheets`
- `output/reading-visual-audit-2026-07-29/summary.json`
- `output/reading-visual-audit-2026-07-29/metrics.json`

## 3. 根本原因

问题不是一个 CSS 数值，而是内容导入、共享渲染器和旧状态共同造成：

1. OCR 导入保留了句号、百分号、引号、括号和所有格后的缺失空格。
2. 少数句子在源数据中被错误拆成两个段落，产生不应有的段间距。
3. A/B/C 分段字母被渲染成独立块，而雅思哥是字母与该段首句内联。
4. 旧前端根据“大写、短句”等特征猜标题，会把普通广告正文错误加粗。
5. 旧左右栏比例可覆盖新默认值，让 CSS 修复看起来没有生效。
6. 匹配矩阵曾额外占用“题目/标记”列，挤压真实作答区域。
7. 描述型匹配只看浏览器总宽度，没有看右侧题目栏实际宽度。
8. 早期回归只确认“控件存在”，没有逐 Part 固定字号、字重、矩阵、表格和溢出指标。

## 4. 已直接修复

### 4.1 文章与内容

- 全题库统一桌面文章字号、字重、行距和段距；
- A/B/C 分段字母改为雅思哥式正文内联粗体；
- 广告、通知、标题、正文、列表、分类、强调语和原文表格使用结构化显示；
- `WORK & TRAVEL USA`、`NETSCAPE` 等特殊版式按原文层级显示；
- 数字使用等高数字，修复 `420988/588980` 等电话号码的视觉错位；
- `J I visa` 修正为 `J-1 visa`；
- `InterExchange` 大小写和品牌粗体统一；
- 本轮额外规范化 477 个数据字符串字段中的高置信度 OCR 间距；
- 重新连接 3 个被错误拆开的原文句子；
- 56 个受影响题库文件的字节数和 SHA-256 清单已同步，未关闭完整性校验。

此前同一轮审查还已完成 2,081 处确定性间距修复、32 处错误 Reading Passage 引用修复，以及 `18`/`1B` 等明确 OCR 字形修复。

### 4.2 题目区和答题方式

- TRUE/FALSE/NOT GIVEN、YES/NO/NOT GIVEN 使用纵向单选；
- 单选、多选、短答、句子、摘要、笔记、流程图、表格和图示题使用对应真实控件；
- 字母型匹配使用雅思哥式矩阵；
- 描述型匹配使用“题目与答案框 + 完整选项库”布局，并支持点击、输入和拖放；
- 选择字母后，答案框保留完整选项文本，不只显示单个字母；
- 多选题按真实 `required_choices` 限制选择数；
- 题目说明保留斜体层级，答案限制词继续加粗；
- 标记题目功能保留，但不再永久占用匹配矩阵列；
- 底部 P1/P2/P3、题号状态和前后翻页与桌面布局统一。

### 4.3 高亮和草稿

- 文章、说明、题干和选项均可高亮、笔记和加入生词本；
- 黄色第一次高亮内可再次选择局部文字，生成雅思哥式粉色二次高亮；
- 精确选中整个既有高亮时显示“取消高亮”，避免误建重复层；
- 新打开练习不恢复旧答案或旧高亮；
- 普通退出不自动保存；
- 只有用户主动点击“保存草稿”才保存答案、高亮、笔记、计时和标记；
- 只有从草稿管理器继续时才恢复这些状态。

## 5. 删除与保留

### 删除

- 删除按大写或句长猜文章标题的旧启发式分支；
- 删除匹配矩阵永久可见的独立“标记”列；
- 删除会覆盖新桌面布局的旧分栏比例版本；
- 删除被新共享模板替代的重复匹配布局和临时扫描文件。

这些代码会造成错误层级、挤压作答空间或让修复看似不生效。

### 保留

- 后端确定性判分及提交前答案隔离；
- 手动草稿；
- 高亮、二次高亮、笔记和个人生词本；
- 可拖动并保存偏好的左右分栏；
- 每题与 Part 计时；
- 暂停、帮助、退出和交卷；
- 新版更完整的键盘输入、清除、标记和来源锚点。

## 6. 当前真题覆盖的 16 类题型

```text
diagram_label_completion
flow_chart_completion
matching_features
matching_headings
matching_information
matching_names
matching_places
matching_sentence_endings
multiple_choice_multiple
multiple_choice_single
note_completion
sentence_completion
short_answer
summary_completion
table_completion
true_false_not_given
```

产品渲染器也兼容 YES/NO/NOT GIVEN；当前 58 套数据没有独立 subtype 样本。

## 7. 实际验证结果

```text
pnpm typecheck:web
passed

pnpm test:web
45 passed

.venv\Scripts\python.exe -m pytest \
  services/api/tests/test_real_question_bank_parity.py \
  services/api/tests/test_session_annotations.py \
  services/api/tests/test_sessions_api.py -q
198 passed, 1 dependency deprecation warning

pnpm test:e2e:web
3 passed
  - 58 套、174 Part 全量桌面控件和溢出检查
  - 16 类题型真实作答交互
  - 判断题、高亮、二次高亮和仅手动草稿恢复

node apps/web/scripts/audit_reading_visuals.mjs
58 tests / 174 Parts / 522 screenshots
0 page errors / 0 anomalies

pnpm --dir apps/web build
compiled and generated 17 static pages
```

构建有两条既有的 `vocabulary.css` Autoprefixer 兼容性提示，建议将 `end` 改为 `flex-end`；它不影响本次阅读工作台构建、渲染或运行。

## 8. 尚未确认的内容和剩余风险

本机雅思哥缓存当前可逐字读取的完整题面集中在剑雅 17、19、20；早期剑雅 4–16、18、21 并不是每篇都在本机缓存中。因此：

- 新版的 174 个 Part 已全部逐页渲染、截图、检查和交互回归；
- 共享样式和题型行为已全量统一；
- 但没有证据时，不声称每一篇早期扫描材料的每一个粗体词都与雅思哥达到像素级逐字一致。

对于没有结构化粗体/居中元数据的早期扫描文章，本轮选择“不猜”，避免再次把普通正文误识别为标题。若以后取得这些页面的完整雅思哥缓存或原卷结构数据，可继续做内容层逐行标注；这不是再改一套全局 CSS 能可靠完成的工作。

## 9. 未发生的外部或高风险操作

- 旧系统代码和数据未修改；
- 历史数据库和用户学习记录未批量改写；
- 未调用真实 Qwen/DeepSeek；
- 未连接生产数据库；
- 未提交、推送、开 PR、上传或部署；
- 未产生费用。

## 10. 用户简单验收建议

1. 在 8001 打开剑雅 5 Test A Part 2，查看广告、J-1、电话号码和 NETSCAPE；
2. 打开剑雅 17 Test 1 Part 3，查看 A/B/C 字母是否与段首同行；
3. 打开任意判断题，确认单选后没有旧橙色堆叠条；
4. 在黄色高亮内再选一小段，确认出现粉色二次高亮；
5. 不点“保存草稿”直接退出并重新进入，答案与高亮应为空；
6. 主动保存草稿后从“管理草稿”继续，状态应恢复。

## 11. 回退方式

不要使用 `git reset --hard`。需要回退时，只恢复本轮相关的：

- `apps/web/components/ExamWorkbench.tsx`
- `apps/web/components/ReadingAnnotationLayer.tsx`
- `apps/web/lib/readingAnnotations.ts`
- `apps/web/app/globals.css`
- `apps/web/app/reading-annotations.css`
- `apps/web/tests/browser/full-question-bank.spec.ts`
- `apps/web/tests/browser/question-type-interactions.spec.ts`
- 受影响的题库 JSON 与 `migration_manifest.json`

这样可避免覆盖工作区中其他尚未提交的用户修改。

## 12. 交卷后详细报告与历史作答回看（2026-07-29）

### 根因

新版服务端判分结果原本已经返回全部题目、题型统计、题目说明、选项、定位分析、关键词、错因、证据句和本次标注；但新版交卷页只展示 Part 概览与少量错题字段。独立“练习记录”页面又使用了另一个简化弹窗，只显示总分与 Part 分数。因此用户从历史记录进入时，看不到原文，也看不到逐题提交答案与正确答案的完整对比。

### 已直接修复

- 交卷后默认进入“错题”筛选；错题包含答错与未作答，默认展开；
- 每题并排显示“我的答案 / 正确答案”，长题干不截断；
- 新增“原文与我的作答记录”，按 Part 恢复原文与右侧逐题答案双栏；
- 报告原文/作答区取消固定窄版上限，桌面端铺满可用区域；双栏调整为约 46% / 54%，高度随视口保持在 680–900px；
- 历史作答区直接复用做题页的 `QuestionGroupControl`，判断、匹配、填空等题型按原做题界面只读还原，不再使用报告专用的简化卡片；
- 删除报告专用的 Part 折叠行，直接复用做题页 40px Part/题号导航结构；仅额外保留正确、错误、未作答的结果颜色；
- 历史记录的“详细报告”进入同一报告页，并按 session 的 `test_id` 重新载入公开原文；
- 新增全部题目、错题、未作答、答对及 Part 筛选；
- 补齐 Part 表现、题型表现、答案解析、定位分析、同义替换、关键词、易错原因、证据句、高亮与笔记；
- 保留原有“概览 / 导出 JSON”和永久删除，不改变既有记录数据；
- 历史报告只读，不会把旧答案或高亮带入新的练习。

### 实际验证

```text
pnpm --dir apps/web typecheck
passed

pnpm --dir apps/web test
48 passed

PYTHONPATH=services/api pytest \
  services/api/tests/test_scoring_parity.py \
  services/api/tests/test_sessions_api.py -q
13 passed, 1 dependency deprecation warning

pnpm --dir apps/web build
compiled and generated 17 static pages
```

系统 Chrome 实测历史记录 `剑雅5 Test A · 22/40`：

- 成功进入 `/practice?session=...`；
- 恢复 3 个 Part 的原文；
- 默认选中“错题 18”；
- 显示 18 张错题/未作答卡并全部展开答案对比；
- 打开的 Part 显示 14 条历史作答记录；
- 题型表现显示 3 类；
- 恢复 87 条本次已提交的高亮/笔记；
- 左右原文与作答记录可独立滚动；
- 报告宽度实测 2609px（2844px 浏览器视口），原文/作答区宽 2458px、高 900px；
- Part 导航实测高 40px，与做题页一致；P1 为 14 个题号，P2/P3 各为 13 个题号；
- 实际切换 P1/P2/P3 后，文章标题、文章内容和对应题组同步更换，历史控件可见但可编辑控件数量为 0。

## 13. 旧版可下载报告迁移（2026-07-29）

### 根因

新版原先只实现了简化的五段式文档生成器；单次练习没有正式 PDF/DOCX，阶段报告只有浏览器打印，导致可下载内容明显少于旧版。旧版正式报告实际包含八个固定部分，问题不在下载按钮，而在报告数据汇总与文档生成内容被简化。

### 已直接修复

- 单次练习、阶段报告、老师作业和老师报告快照统一使用旧版八段式内容：
  1. 给老师的核心摘要；
  2. 练习记录/作业模块与完成情况；
  3. Part 与练习表现；
  4. 总体题型能力矩阵；
  5. 总体错误原因分布；
  6. 代表性错题；
  7. 给老师的教学参考；
  8. 数据口径。
- 单次练习与阶段报告新增正式 PDF 和 DOCX 下载；保留网页详细报告和浏览器打印。
- 代表性错题补齐来源、题干、学生答案、正确答案、原文定位、答案解析、学生确认状态和教师观察建议。
- 空数据表格改为安全生成，避免只有表头时 PDF 下载越界失败。
- PDF 改为嵌入 Windows 等线字体，修复英文被拉成 `N O T G I V E N` 的异常字距。
- 通用错误代码 `incorrect` 在报告中显示为“答案与标准答案不一致”，不再把内部英文代码暴露给用户。

### 实际验证

- 使用本机真实记录 `剑雅5 Test A · 22/40` 通过正式接口下载单次报告和阶段报告；
- 两份 PDF 均为 3 页，逐页渲染检查，无截断、重叠、异常字距或表格越界；
- 两份 PDF 文本抽取均包含 1–8 全部章节；
- 两份 DOCX 均可由 `python-docx` 正常载入，包含 68 个段落、5 个表格和 1–8 全部章节；
- DOCX 页面为 A4（210×297mm），左右页边距各 13mm；
- 本机未安装 LibreOffice/Word，DOCX 无法在本机转换成图片逐页渲染；已完成 OpenXML 结构、内容、页面尺寸和表格完整性验证。

## 14. 单选题与高亮记录默认状态（2026-07-29）

### 根因与修复

- 单选题同时存在透明原生控件和自绘圆圈，特定缩放/焦点状态下会形成双圈；已删除重复自绘控件，统一使用一个原生单选圆圈并保留绿色选中状态、键盘焦点和无障碍名称。
- 历史记录载入事件原先在检测到标注后直接打开右侧 `SESSION ANNOTATIONS` 面板；现改为默认收起，不删除已保存标注，用户需要时仍可主动查看报告中的高亮与笔记。
- 恢复题目开头 `lt ...` 被 OCR 误识别时的精确修复，仅把开头的 `lt ` 还原为 `It `，不改正文中的普通字母组合。

### 实际验证

- 系统 Chrome 打开剑雅5 Test A Part 1，选择 `NOT GIVEN` 后只显示一个原生圆圈和一个绿色圆点；
- 历史详细报告载入后，右侧高亮记录面板不再自动出现；
- `pnpm --dir apps/web typecheck`：通过；
- `pnpm --dir apps/web test`：49/49 通过；
- `pytest services/api/tests -q`：337/337 通过（仅 1 条第三方依赖弃用警告）；
- `git diff --check`：通过，仅提示既有 CRLF 转换信息。
