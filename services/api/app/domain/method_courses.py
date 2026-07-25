from __future__ import annotations

from typing import Any

FOUNDATION_COURSES: tuple[dict[str, Any], ...] = (
    {
        "id": "foundation-exam-workflow",
        "kind": "foundation",
        "title": "G类阅读整套做题流程",
        "objective": "在60分钟内完成三部分，并为检查保留时间。",
        "steps": ["先读题目指令和题数", "按独特词定位，不从头逐句翻译", "先完成确定题，再回到高干扰题", "最后核对未作答、词数和拼写"],
        "traps": ["在一道题上停留过久", "提交前没有检查词数限制", "把自己的常识当作原文证据"],
        "checklist": ["Part 1约15分钟", "Part 2约18分钟", "Part 3约24分钟", "至少3分钟检查"],
    },
    {
        "id": "foundation-locating",
        "kind": "foundation",
        "title": "定位：从题干到原文",
        "objective": "用主体、数字、专有名词和逻辑关系缩小证据范围。",
        "steps": ["圈出不可替换的独特信息", "预测可能出现的同义表达", "先找段落再找句子", "用上下句确认主体和范围"],
        "traps": ["只找原词重复", "找到关键词就立即作答", "忽略代词指向"],
        "checklist": ["主体一致", "时间一致", "范围一致", "证据是完整句意"],
    },
    {
        "id": "foundation-paraphrase",
        "kind": "foundation",
        "title": "同义替换与句意核对",
        "objective": "识别词形、近义词、上下位词和句式转换。",
        "steps": ["先写出题干核心意思", "寻找词形和句式变化", "核对肯定、否定和程度", "把选项还原成完整句意"],
        "traps": ["只看单个同义词", "忽略否定词", "把相关信息误当作等价信息"],
        "checklist": ["谁", "做什么", "在什么条件下", "程度是否相同"],
    },
    {
        "id": "foundation-evidence-boundary",
        "kind": "foundation",
        "title": "证据边界与最短答案",
        "objective": "只复制构成完整答案所必需的词。",
        "steps": ["根据空格前后判断词性", "确认单复数和搭配", "从原文截取最短完整词组", "再次计算单词和数字"],
        "traps": ["多抄限定词", "漏掉必要中心词", "用题干已有词重复作答"],
        "checklist": ["词性正确", "语法通顺", "词数合规", "拼写与原文一致"],
    },
    {
        "id": "foundation-review",
        "kind": "foundation",
        "title": "错题复盘与验证",
        "objective": "把一次错误转化为可验证的下一步训练。",
        "steps": ["记录你的原答案", "找出唯一决定答案的证据", "确认错误发生在哪一步", "做同题型新题验证"],
        "traps": ["只抄正确答案", "把所有错误归为粗心", "看懂解析就认为已经掌握"],
        "checklist": ["能复述证据", "能说明干扰项为什么错", "能写下下次检查动作", "需要用新题达标"],
    },
)

SUBTYPE_METHODS: dict[str, dict[str, Any]] = {
    "true_false_not_given": {
        "title": "TRUE / FALSE / NOT GIVEN",
        "objective": "区分原文支持、明确相反和没有覆盖。",
        "steps": ["拆出主体、范围、时间和程度", "定位对应原文", "逐项比较而不是比较关键词", "支持选TRUE，相反选FALSE，未覆盖选NOT GIVEN"],
        "traps": ["用常识补全", "把部分支持当完整支持", "把没有提到误判为FALSE"],
        "checklist": ["主体相同", "范围相同", "原文有明确反向证据才选FALSE"],
    },
    "yes_no_not_given": {
        "title": "YES / NO / NOT GIVEN",
        "objective": "判断作者观点而不是客观事实。",
        "steps": ["确认题干是观点判断", "找到作者态度或主张", "核对赞同、反对或未表态", "只依据作者立场作答"],
        "traps": ["把他人观点当作者观点", "把事实存在当作者赞同", "没有态度却选NO"],
        "checklist": ["观点归属正确", "态度方向明确", "未表态才选NOT GIVEN"],
    },
    "multiple_choice_single": {
        "title": "单选题",
        "objective": "选择唯一完整满足题干的选项。",
        "steps": ["明确题干问法", "逐项还原完整意思", "为每项找证据或反证", "排除只对一半和范围扩大项"],
        "traps": ["重复原词的选项", "细节正确但答非所问", "过度概括"],
        "checklist": ["选项完整回答题干", "证据覆盖全部含义", "其他项有明确排除理由"],
    },
    "multiple_choice_multiple": {
        "title": "多选题",
        "objective": "在规定数量内独立验证每个选项。",
        "steps": ["先确认选择数量", "逐项定位并记录证据", "分别判断，不让一个选项影响另一个", "最后检查漏选和多选"],
        "traps": ["只找到一个证据就停止", "选择相关但不成立的项", "超过规定数量"],
        "checklist": ["数量正确", "每项都有独立证据", "没有部分成立的干扰项"],
    },
    "matching_information": {
        "title": "信息匹配",
        "objective": "把具体细节匹配到包含该信息的段落。",
        "steps": ["提取题干独特细节", "预测同义替换", "扫描各段寻找信息句", "核对该段确实包含完整信息"],
        "traps": ["按段落主旨匹配", "只凭重复词", "忽略选项可重复规则"],
        "checklist": ["匹配的是细节而非主旨", "信息完整", "已阅读使用规则"],
    },
    "matching_headings": {
        "title": "段落标题匹配",
        "objective": "选择覆盖整段中心功能的标题。",
        "steps": ["概括每段主要功能", "区分主题和例子", "比较标题覆盖范围", "用段尾或转折确认中心"],
        "traps": ["被某个细节词吸引", "标题范围过窄", "只读首句"],
        "checklist": ["覆盖整段", "不是例子", "与其他标题有清楚区别"],
    },
    "matching_features": {
        "title": "特征匹配",
        "objective": "建立对象与观点、行为或特征的准确对应。",
        "steps": ["列出对象名称", "逐个定位对象信息", "记录对应特征", "按题目说明检查能否重复使用"],
        "traps": ["把相邻对象信息串联", "只看名称附近一个词", "忽略选项重复规则"],
        "checklist": ["对象归属明确", "特征完整", "没有跨句误连"],
    },
    "matching_sentence_endings": {
        "title": "句子结尾匹配",
        "objective": "同时满足语法、逻辑和原文证据。",
        "steps": ["先判断主句需要什么成分", "排除语法不通项", "定位原文关系", "验证拼接后的完整含义"],
        "traps": ["只因语法通顺就选择", "忽略因果或转折", "选项含原词但逻辑错误"],
        "checklist": ["语法通顺", "逻辑一致", "原文支持完整句意"],
    },
    "matching_names": {
        "title": "人名匹配",
        "objective": "确认人物与其观点或行为的归属。",
        "steps": ["圈出所有人名及代词", "分别记录观点", "检查转述和引用", "再匹配题干"],
        "traps": ["把作者评价当人物观点", "混淆相邻人物", "忽略he/she/they指代"],
        "checklist": ["说话者明确", "观点方向正确", "代词已回指"],
    },
    "matching_places": {
        "title": "地点匹配",
        "objective": "核对地点与设施、活动或位置关系。",
        "steps": ["建立地点清单", "定位每个地点段落", "记录独特设施或活动", "匹配完整条件"],
        "traps": ["按地名附近关键词猜测", "混淆相邻地点", "忽略方位和限制条件"],
        "checklist": ["地点唯一", "条件完整", "方位关系正确"],
    },
    "sentence_completion": {
        "title": "句子填空",
        "objective": "用最短原文词组完成语法和句意。",
        "steps": ["判断空格词性", "按题序定位", "截取最短完整答案", "检查词数、拼写和单复数"],
        "traps": ["多抄前后词", "改变原文词形", "忽略题干已有词"],
        "checklist": ["词性", "搭配", "词数", "拼写"],
    },
    "summary_completion": {
        "title": "摘要填空",
        "objective": "利用摘要逻辑和原文顺序完成空格。",
        "steps": ["先读完整摘要", "判断每空词性和语义", "按逻辑顺序定位原文", "核对摘要改写后的句意"],
        "traps": ["只按单词匹配", "跳过上下文逻辑", "答案范围过长"],
        "checklist": ["摘要顺序", "同义替换", "语法完整", "词数合规"],
    },
    "note_completion": {
        "title": "笔记填空",
        "objective": "利用层级、并列和项目符号判断答案功能。",
        "steps": ["识别笔记层级", "判断并列项的词性", "定位对应信息段", "保持答案形式一致"],
        "traps": ["忽略标题和上级项目", "并列词性不一致", "抄入解释性多余词"],
        "checklist": ["层级正确", "并列一致", "答案简洁", "拼写准确"],
    },
    "table_completion": {
        "title": "表格填空",
        "objective": "利用行列标题锁定比较维度。",
        "steps": ["读行列标题", "确定每格比较对象", "按表格顺序定位", "核对单位和数字格式"],
        "traps": ["看错行列", "漏单位", "把邻格信息填入"],
        "checklist": ["行对象", "列维度", "单位", "词数"],
    },
    "flow_chart_completion": {
        "title": "流程图填空",
        "objective": "跟随时间或步骤关系完成流程。",
        "steps": ["标出起点和终点", "识别箭头逻辑", "定位过程动词", "核对每步先后和因果"],
        "traps": ["跳步", "把结果当过程", "忽略被动语态"],
        "checklist": ["顺序正确", "动作主体正确", "词性匹配", "答案最短"],
    },
    "diagram_label_completion": {
        "title": "图示标签填空",
        "objective": "结合图中方位和原文描述确定标签。",
        "steps": ["先看图的方向和部件", "圈出位置词", "定位原文结构描述", "核对箭头指向的准确部位"],
        "traps": ["只看名词不看方位", "混淆相邻部件", "忽略图例"],
        "checklist": ["箭头终点", "上下左右", "部件名称", "词数"],
    },
    "short_answer": {
        "title": "简答题",
        "objective": "直接回答疑问词要求，并遵守词数。",
        "steps": ["确认who/where/when/why/how", "定位问题对应句", "只保留能直接回答的词", "检查数字和单位"],
        "traps": ["复制整句", "回答相关但非所问信息", "超过词数"],
        "checklist": ["直接回答疑问词", "信息完整", "无多余词", "格式正确"],
    },
}


def build_method_catalog() -> list[dict[str, Any]]:
    subtype_courses = [
        {
            "id": f"subtype-{subtype}",
            "kind": "subtype",
            "subtype": subtype,
            **content,
        }
        for subtype, content in SUBTYPE_METHODS.items()
    ]
    return [dict(course) for course in FOUNDATION_COURSES] + subtype_courses


def get_method_course(course_id: str) -> dict[str, Any] | None:
    return next((course for course in build_method_catalog() if course["id"] == course_id), None)
