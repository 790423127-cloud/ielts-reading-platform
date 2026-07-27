# 特征匹配题设计复核

## 对比基准

- 旧版参考：`C:\Users\Administrator\AppData\Local\Temp\ielts-old-matching-target.png`
- 新版实现：`C:\Users\Administrator\AppData\Local\Temp\ielts-new-matching-fixed-final.png`
- 句子结尾匹配问题现场：`C:\Users\Administrator\AppData\Local\Temp\codex-clipboard-d0444cfb-816b-4a41-a101-0d3f29dd6bee.png`
- 句子结尾匹配修复后：`C:\Users\Administrator\AppData\Local\Temp\ielts-endings-after-final.png`
- 30% 最窄题目栏验证：`C:\Users\Administrator\AppData\Local\Temp\ielts-endings-narrow-after.png`
- 页面状态：剑雅 5 Test A，Part 1，第 8 题，未作答
- 桌面视口：1280 × 720，设备像素比 1.5
- 移动视口：430 × 932

## 迭代记录

1. P1：新版完整文字匹配题错误复用普通下拉框，导致答案控件缩成右侧小框、题目行留白过大，也没有旧版的选项到答案框交互。
   - 已改为独立的文字匹配题组件。
   - 题目恢复为紧凑行，题号、题干、答案框在同一行。
   - 支持先选选项再点答案框、桌面拖拽、清除答案和标记题目。
2. P2：首轮实现把选项库放在题目列表上方，占用首屏，和旧版聚焦题目行的顺序不同。
   - 已调整为提示、题目列表、选项库的视觉顺序。
   - 纯字母匹配题继续保留原有矩阵答题方式。
3. P1：在较窄的桌面题目栏或已保存的分栏比例下，普通 `fr` 轨道会被选项库的最小内容宽度撑开，导致答案框被推到可视区域右侧；整张选项卡也没有绑定拖拽。
   - 分栏改为两侧 `minmax(0, fr)`，并为文章栏、题目栏和匹配题容器补齐最小宽度与横向溢出约束。
   - 拖拽事件从选项字母扩大到整张选项卡，保留点击选择和键盘选择。

## 最终检查

- 版式：左右文章/题目工作台、紧凑匹配题行、底部题号导航与旧版的核心做题结构一致。
- 字体与颜色：保留新版现有设计令牌，不回退新版已经更清晰的顶栏和中文提示。
- 交互：实测选择 J，再点击第 8 题答案框，显示 `J Guide to the Art of the Australian Desert`；清除后恢复未作答。句子结尾匹配题的整张选项卡均可拖拽。
- 自适应：430px 宽度下题目与答案框改为单列，页面 `scrollWidth = innerWidth = 430`，无整页横向溢出。
- 桌面窄分栏：文章栏调到 70%、题目栏调到允许的最小 30% 后，工作台 `scrollWidth = clientWidth = 1264`，题目栏答案框仍完全位于可视区域内。
- 数据：测试答案已清除，未交卷、未生成成绩。
- 自动检查：匹配题测试和项目现有 Node 测试共 21 项通过；TypeScript 检查通过；`git diff --check` 通过（仅有仓库原有行尾提示）。

## 结果

final result: passed
