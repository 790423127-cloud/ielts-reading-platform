from __future__ import annotations

"""Deterministic, offline IELTS GT Reading method-course catalogue.

The method-course page is a read-only instruction manual.  It does not call an
AI provider, score the learner, inspect practice history, or depend on question
bank availability.  Every course teaches a stable exam-day procedure.
"""

import copy
from typing import Any

COURSE_BLUEPRINTS: tuple[dict[str, Any], ...] = (
    {
        "id": "true_false_not_given",
        "title": "TRUE / FALSE / NOT GIVEN",
        "family": "judgement",
        "family_label": "判断题",
        "category": "judgement",
        "summary": "先判断原文有没有说，再判断一致还是相反；不使用常识补全。",
        "recognition": ["题目判断的是事实信息", "选项为 TRUE、FALSE、NOT GIVEN", "题目通常按原文顺序出现"],
        "traps": ["没找到相同单词就直接选 NOT GIVEN", "忽略 all、some、always 等限定词", "用自己的常识代替原文证据"],
    },
    {
        "id": "yes_no_not_given",
        "title": "YES / NO / NOT GIVEN",
        "family": "judgement",
        "family_label": "判断题",
        "category": "judgement",
        "summary": "锁定作者或说话者的观点来源，再判断观点一致、相反或没有表达。",
        "recognition": ["题目判断观点、主张或看法", "选项为 YES、NO、NOT GIVEN", "必须确认观点属于谁"],
        "traps": ["把事实存在误当成作者同意", "混淆不同人物的观点", "根据态度词猜测而不核对完整句"],
    },
    {
        "id": "multiple_choice_single",
        "title": "单项选择题",
        "family": "choice",
        "family_label": "选择题",
        "category": "single_choice",
        "summary": "先明确题目焦点并预测答案方向，再逐项寻找支持或排除证据。",
        "recognition": ["一道题只选择一个答案", "题干常问原因、目的、观点或主旨", "选项通常都含有原文相关词"],
        "traps": ["看到原文同词就选择", "只证明选项部分正确", "选项说的是原文事实却没有回答题目"],
    },
    {
        "id": "multiple_choice_multiple",
        "title": "多项选择题",
        "family": "choice",
        "family_label": "选择题",
        "category": "multiple_choice",
        "summary": "确认需要选择的数量，为每个候选选项分别寻找独立证据。",
        "recognition": ["题目明确要求选择两个或更多答案", "多个正确答案可能分散在不同位置", "最终答案数量必须完全符合要求"],
        "traps": ["只找到一个证据就连带选择相似选项", "少选或多选", "把部分正确的选项算作正确"],
    },
    {
        "id": "matching_information",
        "title": "段落信息匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "先判断题目要找的信息功能，再用独特关键词和同义替换验证整段。",
        "recognition": ["题目问哪一段包含某条信息", "段落通常用字母编号", "同一段有时可以重复使用"],
        "traps": ["只按相同关键词匹配", "忽略题目找的是原因、例子还是观点", "没有检查选项能否重复"],
    },
    {
        "id": "matching_headings",
        "title": "段落标题匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "用自己的话概括整段中心，排除只对应例子或局部细节的标题。",
        "recognition": ["给出 List of Headings", "需要为段落选择最合适标题", "多余标题通常是干扰项"],
        "traps": ["把段落中的醒目例子当成主旨", "只看首句不看转折和结尾", "因为出现同词就选标题"],
    },
    {
        "id": "matching_features",
        "title": "特征匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "建立对象清单，定位每个对象的范围，再比较相近对象的真正差异。",
        "recognition": ["字母代表人物、理论、地点或类别", "题目描述观点、行为或特征", "选项可能允许重复"],
        "traps": ["没有先明确每个字母代表谁", "两个对象都提到同一主题就混淆", "忽略复用规则"],
    },
    {
        "id": "matching_sentence_endings",
        "title": "句子结尾匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "先预测句子需要表达的关系，再同时检查语法连接和原文意义。",
        "recognition": ["题目给出句子前半部分和一组结尾", "连接后必须语法完整", "题目通常按文章顺序出现"],
        "traps": ["只看语法通顺不核对原文", "看选项后才开始猜句意", "忽略代词、单复数或逻辑关系"],
    },
    {
        "id": "matching_names",
        "title": "人名匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "把每个人的观点、行为和限定条件整理成表，再完成交叉匹配。",
        "recognition": ["选项是一组人名或说话者", "题目描述人物观点或经历", "同一人物可能对应多题"],
        "traps": ["只记人物出现的位置不记观点", "混淆共同主题和个人差异", "忽略否定或让步表达"],
    },
    {
        "id": "matching_places",
        "title": "地点匹配",
        "family": "matching",
        "family_label": "匹配题",
        "category": "matching",
        "summary": "先建立地点与功能、位置、限制条件的对应表，再核对题目描述。",
        "recognition": ["选项是一组地点、设施或区域", "题目描述功能、位置或服务", "同一地点可能被重复使用"],
        "traps": ["只根据地点名附近的一句话作答", "混淆位置和功能", "没有核对开放时间、对象等限制"],
    },
    {
        "id": "sentence_completion",
        "title": "句子填空",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "利用空格前后预测词性和含义，按顺序定位并填写最短完整原文答案。",
        "recognition": ["需要补完整句子", "题目给出明确词数上限", "答案通常按文章顺序出现"],
        "traps": ["把词数上限当成必须写满", "重复题干已经给出的词", "找到相关句却没有检查整句语法"],
    },
    {
        "id": "summary_completion",
        "title": "摘要填空",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "先理解摘要的逻辑结构，再利用前后句和同义改写锁定答案区域。",
        "recognition": ["题目是一段连续摘要", "摘要顺序通常对应原文某一区域", "可能给词库，也可能要求原文词"],
        "traps": ["逐空孤立作答，不看摘要逻辑", "没有确认是否必须使用词库", "抄入相关但词性不合适的词"],
    },
    {
        "id": "note_completion",
        "title": "笔记填空",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "根据项目符号和标题判断信息层级，用语法与并列结构预测答案。",
        "recognition": ["题目以标题、缩进或项目符号组织", "答案是压缩后的关键信息", "相邻空格常具有并列关系"],
        "traps": ["忽略标题限定的主题", "没有利用并列项目预测词性", "多抄解释性内容导致超词"],
    },
    {
        "id": "table_completion",
        "title": "表格填空",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "利用行列标题确定比较维度，横向和纵向同时验证答案。",
        "recognition": ["题目用行列展示对比信息", "表头决定答案类型", "同一行或列通常保持平行结构"],
        "traps": ["只看单元格附近文字不看表头", "把相邻行的信息填错位置", "数字、单位或比较对象不完整"],
    },
    {
        "id": "flow_chart_completion",
        "title": "流程图填空",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "先识别流程起点、终点和箭头关系，再按时间或步骤顺序定位。",
        "recognition": ["题目使用箭头或阶段展示过程", "答案常是动作、材料或结果", "原文通常按流程顺序描述"],
        "traps": ["忽略箭头方向", "混淆动作和动作产生的结果", "没有检查被动语态和词形"],
    },
    {
        "id": "diagram_label_completion",
        "title": "图示标签题",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "理解图中方向、部件和编号关系，核对答案是否适合对应位置。",
        "recognition": ["题目要求标注图中部件或位置", "编号和空间方向是重要定位线索", "答案通常是部件名、材料或方向"],
        "traps": ["只找到原文词却不核对图中位置", "重复图上已经给出的词", "忽略方向、内外或上下关系"],
    },
    {
        "id": "short_answer",
        "title": "简答题",
        "family": "completion",
        "family_label": "填空与简答",
        "category": "gap_fill",
        "summary": "由问题词判断答案类型，只填写能直接回答问题的最短必要信息。",
        "recognition": ["题目是 who、where、when、why、how 等直接问题", "通常有词数上限", "答案必须来自原文"],
        "traps": ["抄写整句话导致超词", "回答了相关信息但没有回应问题词", "加入题目未要求的解释"],
    },
)

_BLUEPRINT_BY_ID = {item["id"]: item for item in COURSE_BLUEPRINTS}


FAMILY_TEACHING: dict[str, dict[str, Any]] = {
    "judgement": {
        "goal": "把题干和原文放在一起比较，只回答三件事：原文说了、原文说反了、原文没有告诉我。",
        "before_you_start": ["圈出题干说的是谁或什么", "圈出时间、数量和 all / some 等范围词", "提醒自己：我只相信文章，不使用常识"],
        "difficulty_ladder": [
            {"level": "简单题", "signal": "题干对象清楚，原文附近有直接同义句。", "action": "定位同一对象，比较意思；一致就选 TRUE/YES，明确相反就选 FALSE/NO。"},
            {"level": "普通题", "signal": "题干换了说法，或改变了时间、数量、可能性。", "action": "把限定词一个一个对齐，再判断整句关系，不按一个相同单词作答。"},
            {"level": "困难题", "signal": "多个人物、多段时间、观点来源混在一起，或看起来像 NOT GIVEN。", "action": "先写“同一对象吗—原文说了吗—关系相同吗”三问；三问没有走完，不选答案。"},
        ],
        "hard_rescue": [
            "停下来，不要在 TRUE、FALSE、NOT GIVEN 之间凭感觉来回改。",
            "把题干缩成最小信息：谁 + 做什么 + 什么范围/时间。",
            "只读最相关句及前后各一句，确认观点到底属于谁。",
            "先问“原文有没有完整谈到这件事”；没有足够信息才是 NOT GIVEN。",
            "如果谈到了，再问是同义还是明确相反；最后才写答案。",
        ],
        "time_plan": {"easy": "约 40–60 秒", "normal": "约 60–90 秒", "hard": "最多 2 分钟；先标记，再做后题后回来"},
    },
    "choice": {
        "goal": "找到真正回答题目问题的选项，而不是找到一个在文章里出现过的句子。",
        "before_you_start": ["圈出题目问的是原因、目的、观点还是事实", "先用自己的话预测答案方向", "记住：每个选项都要单独验明正身"],
        "difficulty_ladder": [
            {"level": "简单题", "signal": "正确项是原文一句话的清楚改写，其他项明显不相关。", "action": "先定位证据，再确认该选项完整回答题目。"},
            {"level": "普通题", "signal": "多个选项都出现过，但只有一个回答了题目的真正焦点。", "action": "给每项写“支持/反对/没回答”，不要只看关键词。"},
            {"level": "困难题", "signal": "选项都像对的，或每项只有一半正确。", "action": "拆开选项的对象、动作、原因和范围；任何一个关键部分不符，整项就错。"},
        ],
        "hard_rescue": [
            "把选项暂时盖住，只读题干，说出“它到底问什么”。",
            "回原文画出能直接回答这个问题的一到两句证据。",
            "逐项检查对象、时间、因果、程度，不能因为出现同词就通过。",
            "排除“原文提过但没回答问题”和“前半对、后半错”的选项。",
            "剩两项时，不比较哪项更像；比较哪项有完整直接证据。",
        ],
        "time_plan": {"easy": "约 60 秒", "normal": "约 90 秒", "hard": "最多 2 分钟；保留候选并继续"},
    },
    "matching": {
        "goal": "先给每段或每个对象贴一张小标签，再把题目描述与正确标签连接起来。",
        "before_you_start": ["确认选项能不能重复使用", "判断题目找主旨、细节、人物还是地点", "先找名字、数字、转折等明显路标"],
        "difficulty_ladder": [
            {"level": "简单题", "signal": "有独特人名、地点、数字或专业词可以快速定位。", "action": "用路标找到候选位置，再读完整句验证。"},
            {"level": "普通题", "signal": "原文使用同义词，两个段落或对象都谈到相似主题。", "action": "给候选各写一句“它主要做什么”，再比较题目要找的功能。"},
            {"level": "困难题", "signal": "选项很多、内容重复、主旨藏在转折后，或同一选项可复用。", "action": "先做最独特的题；难题保留两个候选，用排除表最后解决。"},
        ],
        "hard_rescue": [
            "先跳过没有任何路标的题，完成有人名、数字或特殊名词的题。",
            "在候选段旁只写 5–8 个字的功能标签，例如“解释原因”“反对旧方法”。",
            "检查转折词 but / however / instead 后面的重点，不能只读首句。",
            "两个候选都像时，问哪一个完整表达题目，哪一个只碰到一个词。",
            "最后核对复用规则和剩余选项，不用“一一对应”的想当然规则。",
        ],
        "time_plan": {"easy": "约 45–70 秒", "normal": "约 90 秒", "hard": "先跳过，整组最后用 2 分钟复核"},
    },
    "completion": {
        "goal": "找到原文里的正确词，并让它在空格里同时满足意思、语法、词数和拼写。",
        "before_you_start": ["把词数上限圈起来", "看空格前后预测词性和答案种类", "记住：最多几个词，不是必须写满几个词"],
        "difficulty_ladder": [
            {"level": "简单题", "signal": "空格附近给出明显定位词，答案是原文中的直接名词或数字。", "action": "定位后抄最短完整答案，再检查词数和拼写。"},
            {"level": "普通题", "signal": "题干有同义改写，需要靠语法判断单复数或词形。", "action": "先预测词性和含义，再寻找同义句；把答案放回整句朗读。"},
            {"level": "困难题", "signal": "多个相邻名词都像答案、答案边界不清，或表格/图示关系复杂。", "action": "先写候选短语，再逐个删词；保留最短但语法和意思仍完整的原文连续词。"},
        ],
        "hard_rescue": [
            "不盲找单词，先说空格需要“什么词性 + 什么信息”。",
            "用题干中最特别的名词、数字和逻辑关系定位同义句。",
            "找到候选后，检查中心词必须保留，题干已有的词不要重复。",
            "把答案放回空格读一遍，核对单复数、搭配和整句意思。",
            "最后数词、查拼写；仍不确定就写最短有证据的连续原文词。",
        ],
        "time_plan": {"easy": "约 35–50 秒", "normal": "约 60–80 秒", "hard": "最多 90 秒；留空标记后继续"},
    },
}


COURSE_TEACHING: dict[str, dict[str, Any]] = {
    "true_false_not_given": {
        "plain_language": "题目给你一句“事实”。你要像小侦探一样，只看文章证据，判断它是说对了、说反了，还是文章根本没说够。",
        "memory_sentence": "先问“说没说”，再问“同不同”。",
        "easy_rule": "看到同一人物和同一时间的直接改写，比较整句意思即可。",
        "hard_signals": ["题干把 some 偷换成 all", "原文只说 A，题干追问 A 的原因", "题干与原文谈的是不同时间或人群"],
        "special_rules": ["TRUE = 原文明确支持", "FALSE = 原文明确给出相反信息", "NOT GIVEN = 原文不足以判断", "没找到相同词不等于 NOT GIVEN"],
        "mini_example": {"context": "文章：Some library members borrow e-books at night.", "question": "题目：All library members borrow e-books at night.", "answer": "FALSE", "reasoning": ["对象相同：library members。", "文章说 some（一些），题目说 all（全部）。", "范围被扩大，意思明确相反，所以选 FALSE。"]},
    },
    "yes_no_not_given": {
        "plain_language": "这次不是查事实，而是查“某个人同不同意”。先找到这句话是谁的观点，再判断他赞成、反对，还是没有表态。",
        "memory_sentence": "先找说话的人，再看他同不同意。",
        "easy_rule": "作者直接使用 should、best、wrong 等态度词时，先确认观点归属再比较。",
        "hard_signals": ["文章介绍观点但作者没有同意", "不同专家的观点放在同一段", "作者只描述事实，题干却说他支持某主张"],
        "special_rules": ["YES = 指定人物的观点一致", "NO = 指定人物明确持相反观点", "NOT GIVEN = 没有表达该态度", "文章提到某观点不代表作者赞成"],
        "mini_example": {"context": "文章：Dr Lee argues that free buses are the best solution. The writer later calls this idea unrealistic.", "question": "题目：The writer believes free buses are the best solution.", "answer": "NO", "reasoning": ["题目问 writer，不是 Dr Lee。", "作者说 unrealistic，表示不赞成。", "观点来源和态度都核对后，答案是 NO。"]},
    },
    "multiple_choice_single": {
        "plain_language": "四个答案里只有一个真正回答题目。其他答案可能在文章里出现过，但它们回答了别的问题，或只对了一半。",
        "memory_sentence": "出现过不算对，答到问题才算对。",
        "easy_rule": "先用自己的话说出问题要找什么，再选有完整证据的唯一选项。",
        "hard_signals": ["四项都含原文词", "正确项使用完全不同的同义表达", "干扰项前半正确、后半错误"],
        "special_rules": ["题干焦点比关键词更重要", "一个关键部分错，整个选项就错", "正确项必须有完整证据", "排除项也要说得出错在哪里"],
        "mini_example": {"context": "文章：The museum moved the tour to mornings because the galleries are quieter then.", "question": "题目：Why was the tour moved? A 更便宜 B 更安静 C 展品更多", "answer": "B 更安静", "reasoning": ["问题词 Why 要找原因。", "because 后面给出原因：quieter。", "B 是完整同义答案；其他项没有证据。"]},
    },
    "multiple_choice_multiple": {
        "plain_language": "这像把几颗正确积木从一盒积木里找出来。每一颗都必须有自己的证据，而且最后数量一个也不能多、一个也不能少。",
        "memory_sentence": "选几个先圈住，每一项单独找证据。",
        "easy_rule": "先圈题目要求的答案数量，再为每个选项分别标记有证据或无证据。",
        "hard_signals": ["多个答案分散在不同段落", "两项意思很像但只有一项完全符合", "找到一个正确项后容易顺手选相关项"],
        "special_rules": ["答案数量必须完全正确", "每个正确项都需独立证据", "两项相似不代表一起正确", "部分符合仍然是错误项"],
        "mini_example": {"context": "文章：Visitors should bring water and a sun hat. Food is provided by the centre.", "question": "题目：Choose TWO things visitors should bring. A water B food C sun hat", "answer": "A 和 C", "reasoning": ["先圈 TWO。", "water 有直接证据，A 保留。", "food 是中心提供，不是游客带，B 排除；sun hat 有证据，C 保留。"]},
    },
    "matching_information": {
        "plain_language": "题目不是问哪段“提过这个词”，而是问哪段完成了某件事，例如解释原因、举例子、作比较。",
        "memory_sentence": "找信息的作用，不只找相同的词。",
        "easy_rule": "先圈题目中的独特路标，再验证候选段是否完整表达所问信息。",
        "hard_signals": ["多个段落都有同一个主题词", "题目问例子而段落只给观点", "同一段允许被使用多次"],
        "special_rules": ["题目找原因就必须有因果", "题目找例子就必须有具体实例", "关键词只负责带路，不负责决定答案", "先检查段落能否重复使用"],
        "mini_example": {"context": "A段介绍新公园。B段说公园建在车站旁，因此上班族容易到达。", "question": "题目：a reason why the park is easy to reach", "answer": "B段", "reasoning": ["题目找 reason。", "B 段有“因此”并解释车站位置带来的便利。", "A 只介绍公园，没有给原因。"]},
    },
    "matching_headings": {
        "plain_language": "你要给整段文章取一个最合适的小标题。标题要像一把大伞，能罩住整段，而不只是罩住一个例子。",
        "memory_sentence": "标题管整段，例子只管一小块。",
        "easy_rule": "先不看标题选项，用一句自己的话概括段落，再去找意思最接近的标题。",
        "hard_signals": ["段首先讲旧观点，转折后才是重点", "醒目的名字或数字只是例子", "两个标题都相关但一个范围太窄"],
        "special_rules": ["先概括，后看选项", "重点看转折和结尾", "标题要覆盖大部分句子", "同词最多是线索，不是答案"],
        "mini_example": {"context": "段落先说旧自行车很重，随后介绍新材料让车更轻、更快，最后说明这改变了城市出行。", "question": "标题：A 旧自行车的重量 B 新材料带来的改变", "answer": "B", "reasoning": ["旧自行车只在开头出现，是背景。", "整段主要讲新材料及其影响。", "B 能罩住大部分内容，A 太窄。"]},
    },
    "matching_features": {
        "plain_language": "把人物、理论或物品当成几只不同颜色的盒子。先记录每只盒子的特点，再把题目放进正确盒子。",
        "memory_sentence": "先做对象小档案，再开始连线。",
        "easy_rule": "每找到一个对象，就记录“他做了什么、怎么看、有什么限制”。",
        "hard_signals": ["两个对象谈到相同主题", "选项可以重复", "题目用同义词改写对象的特点"],
        "special_rules": ["共同主题不等于共同观点", "先确定选项代表谁", "记录真正不同点", "提交前检查复用规则"],
        "mini_example": {"context": "Mia 喜欢线上课程的灵活时间；Noah 喜欢课堂上的即时提问。", "question": "题目：values being able to study at any time", "answer": "Mia", "reasoning": ["at any time 是 flexible time 的改写。", "Mia 的独特点正是时间灵活。", "Noah 说的是提问，不是时间。"]},
    },
    "matching_sentence_endings": {
        "plain_language": "给句子的前半截找到正确尾巴。这个尾巴既要接得通顺，也要和原文说的一模一样。",
        "memory_sentence": "语法要接上，意思也要对上。",
        "easy_rule": "先判断句子需要原因、结果还是目的，再看结尾选项。",
        "hard_signals": ["两个结尾语法都通顺", "代词指向不同对象", "选项有原文词但因果关系相反"],
        "special_rules": ["语法正确只是第一关", "意义必须有原文证据", "留意代词和单复数", "通常可按文章顺序定位"],
        "mini_example": {"context": "文章：The shop extended its hours so commuters could visit after work.", "question": "The shop stayed open longer in order to ... A reduce costs B serve workers", "answer": "B serve workers", "reasoning": ["in order to 要接目的。", "so commuters could visit after work 表示服务下班人群。", "B 语法和意思都成立。"]},
    },
    "matching_names": {
        "plain_language": "文章里有好几个人说话。你要给每个人做一张“观点卡”，不要把甲说的话放到乙的卡片里。",
        "memory_sentence": "名字先框住，观点写旁边。",
        "easy_rule": "看到人名后读到下一个人名为止，记录态度、行为和限定条件。",
        "hard_signals": ["作者转述多个人的观点", "人物先赞成一部分再反对另一部分", "同一个人相隔多段再次出现"],
        "special_rules": ["观点必须归到正确人物", "记录转折后的最终态度", "同一人物可能对应多题", "不要只记出现位置"],
        "mini_example": {"context": "Anna 说价格最重要；Ben 认为位置重要，但后来强调服务质量才决定选择。", "question": "题目：believes service is the deciding factor", "answer": "Ben", "reasoning": ["题干关键词 deciding factor 对应“才决定”。", "Ben 转折后的最终重点是服务。", "Anna 只谈价格。"]},
    },
    "matching_places": {
        "plain_language": "把每个地点看成一间有不同功能的房间。记清它在哪里、能做什么、谁能用、什么时候能用。",
        "memory_sentence": "地点名旁写：位置、功能、限制。",
        "easy_rule": "先用大写地点名定位，再核对功能和开放对象。",
        "hard_signals": ["两个地点提供相似服务", "地点和服务不在同一句", "开放时间或使用人群不同"],
        "special_rules": ["位置相同不代表功能相同", "限制条件属于答案的一部分", "地点可能重复使用", "读地点附近完整信息块"],
        "mini_example": {"context": "North Hall 有电脑，仅供会员使用；East Room 向所有访客提供安静阅读区。", "question": "题目：a quiet place available to everyone", "answer": "East Room", "reasoning": ["quiet place 对应安静阅读区。", "everyone 对应所有访客。", "North Hall 有会员限制，不符合 everyone。"]},
    },
    "sentence_completion": {
        "plain_language": "句子缺了一块。先看缺口形状，猜它需要名词、数字还是别的，再从原文找一块大小正好的词放进去。",
        "memory_sentence": "先猜词性，再找原词，最后放回句子读。",
        "easy_rule": "空格前有 a/an 常提示单数可数名词；数字后常需要单位或名词。",
        "hard_signals": ["题干已经给出答案短语的一部分", "两个相邻名词都像答案", "原文与题干使用不同语法结构"],
        "special_rules": ["答案通常按文章顺序", "必须遵守词数上限", "不重复题干已有词", "最短完整答案优先"],
        "mini_example": {"context": "文章：Visitors receive a reusable bottle at reception.", "question": "Visitors are given a ______ at reception.（NO MORE THAN TWO WORDS）", "answer": "reusable bottle", "reasoning": ["a 后面需要单数名词短语。", "原文直接给出 reusable bottle。", "共两词，符合上限，放回句子也通顺。"]},
    },
    "summary_completion": {
        "plain_language": "摘要像把一段长故事压短了。先读懂短故事的顺序，再沿着原文同一小块区域依次找答案。",
        "memory_sentence": "先读整段摘要，再从同一原文区域顺着填。",
        "easy_rule": "先看摘要标题和首尾句，确定主题；相邻空格通常按原文顺序出现。",
        "hard_signals": ["摘要大量使用同义改写", "一个空填错会影响后面逻辑", "题目可能给词库且有多余词"],
        "special_rules": ["不要把每个空孤立处理", "先确认用词库还是原文词", "利用前后逻辑和并列结构", "填完重读整段摘要"],
        "mini_example": {"context": "文章：Seeds are first dried, then stored in cool rooms.", "question": "摘要：The seeds are dried before being kept in ______ rooms.", "answer": "cool", "reasoning": ["before 对应 first...then 的顺序。", "rooms 前需要形容词。", "原文 cool 正好修饰 rooms。"]},
    },
    "note_completion": {
        "plain_language": "笔记把信息分成标题、大点和小点。先看空格属于哪一层，再判断它要填原因、例子、材料还是结果。",
        "memory_sentence": "先看标题和缩进，再看空格。",
        "easy_rule": "同一组项目符号通常使用相同词性和信息类型，可以互相提示。",
        "hard_signals": ["笔记省略了很多语法词", "标题限制答案范围", "相邻项目看似相似但属于不同层级"],
        "special_rules": ["标题决定主题范围", "缩进表示信息层级", "并列项应保持结构平行", "答案可短但必须完整"],
        "mini_example": {"context": "文章：The course fee includes books and online videos.", "question": "Fee includes: • books • ______", "answer": "online videos", "reasoning": ["项目符号表示并列内容。", "books 是名词，空格也需要名词。", "原文另一个并列项目是 online videos。"]},
    },
    "table_completion": {
        "plain_language": "表格像一个有横街和竖街的地图。答案必须同时住在正确的行和正确的列，不能只看旁边一个格子。",
        "memory_sentence": "先看列名，再看行名，交叉决定答案。",
        "easy_rule": "把所在行标题和列标题合成一个问题，再去原文寻找答案。",
        "hard_signals": ["相邻行数据容易串位", "数字缺少单位", "同一列的答案词性必须平行"],
        "special_rules": ["行列标题共同限制答案", "横向纵向都要核对", "数字和单位按题意保留", "完成后逐行检查是否错位"],
        "mini_example": {"context": "文章：Adult tickets cost £12; child tickets cost £7.", "question": "表格：Child | Price | ______", "answer": "£7", "reasoning": ["行是 Child，列是 Price。", "不能误填 Adult 的 £12。", "交叉位置对应 child tickets cost £7。"]},
    },
    "flow_chart_completion": {
        "plain_language": "流程图是一条一步接一步的小路。先找到起点和箭头方向，再看每个空格需要动作、材料还是结果。",
        "memory_sentence": "沿箭头走：先后不能倒，动作结果要分清。",
        "easy_rule": "在原文圈 first、then、after、finally，按同一顺序对应流程框。",
        "hard_signals": ["原文使用被动语态", "流程图省略主语", "动作与产生的结果容易混淆"],
        "special_rules": ["箭头决定顺序", "先判断空格要动作还是物品", "留意主动被动变化", "前后步骤必须逻辑相连"],
        "mini_example": {"context": "文章：First the fruit is washed. It is then cut into small pieces.", "question": "流程：fruit → washed → ______", "answer": "cut into small pieces", "reasoning": ["箭头要求下一步。", "then 标出洗净后的动作。", "答案是动作 cut into small pieces，不是 fruit。"]},
    },
    "diagram_label_completion": {
        "plain_language": "图上的箭头在问“这个部位叫什么”。先看箭头指向里面、外面、上面还是下面，再去文章找对应名称。",
        "memory_sentence": "先看箭头指哪里，再找那个部位的名字。",
        "easy_rule": "先理解已有标签，利用上下、内外、左右关系预测缺失部位。",
        "hard_signals": ["多个部件名称连续出现", "文字顺序与图中空间顺序不同", "箭头指向连接处而非整个物体"],
        "special_rules": ["位置和名称必须同时正确", "图上已有词不要重复", "方向词是重要证据", "标签使用最短完整部件名"],
        "mini_example": {"context": "文章：Water enters through the upper pipe and leaves through the lower valve.", "question": "图中箭头指向下方出口：______", "answer": "lower valve", "reasoning": ["箭头指向下方出口。", "原文 lower 对应下方，valve 是部件名。", "upper pipe 是入口，位置不符。"]},
    },
    "short_answer": {
        "plain_language": "问题问什么，你就用原文最短的话直接回答什么。问人就写人，问地点就写地点，不要把整句话搬过来。",
        "memory_sentence": "先看问题词，只写它要的那一小块。",
        "easy_rule": "把 who/where/when/how many 翻成答案类型，再定位对应原文信息。",
        "hard_signals": ["答案旁边有许多无关修饰词", "why/how 的答案边界较长", "题干词数限制很小"],
        "special_rules": ["答案必须直接回应问题词", "词数上限不是目标", "不要加入自己的解释", "保留中心词和必要修饰词"],
        "mini_example": {"context": "文章：The meeting will take place in the town library on Friday.", "question": "Where will the meeting take place?（NO MORE THAN THREE WORDS）", "answer": "the town library", "reasoning": ["Where 要地点。", "地点是 the town library。", "on Friday 是时间，不需要写；答案三词，符合上限。"]},
    },
}


FAMILY_FOUNDATIONS: dict[str, dict[str, Any]] = {
    "judgement": {
        "title": "判断题的证据比较基础",
        "intro": "不要先猜 TRUE、FALSE 或 NOT GIVEN。先把题干拆成对象、动作、时间、数量和程度，再与原文逐格比较。",
        "rules": [
            {"signal": "题干和原文是不是同一个人或同一件事", "meaning": "对象不同，后面的比较没有意义", "action": "先框出人名、群体、物品或机构，确认指代一致", "example": "原文说 visitors，题目却说 staff：先判定对象不同"},
            {"signal": "时间：now / before / in 2020 / usually", "meaning": "同一件事在不同时间可能真假不同", "action": "把时间词单独圈出，不能只比较动作", "example": "used to open ≠ now opens"},
            {"signal": "数量：all / some / most / only / none", "meaning": "范围大小是判断题最常见的偷换", "action": "逐字比较范围；some 不能自动推出 all", "example": "Some members joined → All members joined 为 FALSE"},
            {"signal": "程度：may / can / must / always / sometimes", "meaning": "可能、能力、必须和总是并不相同", "action": "把情态词和频率词当作证据的一部分", "example": "may reduce ≠ will always prevent"},
            {"signal": "原因和结果是否完整出现", "meaning": "原文有结果，不代表原文说明了题目所说的原因", "action": "分别问：结果说了吗？这个原因也说了吗？", "example": "原文说销量下降；未说明因价格下降，所以原因可能 NG"},
            {"signal": "比较词：more / less / better / the same", "meaning": "比较对象或方向一变，意思就变", "action": "写成 A 与 B 比较，再核对谁高谁低", "example": "A is cheaper than B ≠ B is cheaper than A"},
            {"signal": "原文只谈 A，题目追问 A 的细节", "meaning": "没有足够信息不等于相反", "action": "找不到该关系时选 NOT GIVEN，而不是 FALSE", "example": "说 Tom 搬家，没说为什么搬家：原因题为 NG"},
            {"signal": "作者、专家、受访者等多个观点来源", "meaning": "一句话被谁说，决定 YES/NO 的判断对象", "action": "在观点旁写说话者名字，再比较态度", "example": "专家赞成，不代表作者赞成"},
        ],
    },
    "choice": {
        "title": "选择题的题干与选项拆解基础",
        "intro": "正确选项不是“文章里出现过”的选项，而是完整回答题干问题、每一部分都有证据的选项。",
        "rules": [
            {"signal": "Why / What / How / main purpose", "meaning": "问题词决定要找原因、事实、方式或主旨", "action": "先把题目改写成中文小问题，再看选项", "example": "Why...? 只找原因，不能选一个相关结果"},
            {"signal": "还没看选项时能否预测答案方向", "meaning": "先预测可防止被选项带跑", "action": "写下大概答案，例如“某项服务更方便”", "example": "问搬迁原因：先预测要找 because 后的信息"},
            {"signal": "选项里的人、动作、条件、结果", "meaning": "选项任一关键部分错误，整项就错", "action": "把长选项用斜线拆成 3–4 小块逐块核对", "example": "对象对、原因错：该选项仍然错误"},
            {"signal": "选项大量照抄原文词", "meaning": "同词项常是“提过但没回答”的干扰项", "action": "回到题干，问它是否真的回答问题", "example": "文章提到 price，题目问 purpose；出现 price 不等于答案"},
            {"signal": "选项前半正确、后半新增信息", "meaning": "半对半错仍是错误选项", "action": "用原文分别验证前半和后半", "example": "更快有证据，“而且更便宜”无证据：整项排除"},
            {"signal": "选项说的是相关事实，却偏离题干焦点", "meaning": "真实不等于答题", "action": "给选项标“回答 / 相关但没回答 / 相反 / 无证据”", "example": "题目问原因，选项只描述地点：没回答"},
            {"signal": "only / always / completely / never", "meaning": "绝对词需要同样强的原文证据", "action": "重点查原文是否真的达到绝对程度", "example": "often 不能证明 always"},
            {"signal": "剩下两个都很像", "meaning": "靠语感比较会反复改答案", "action": "分别写出直接证据；没有完整证据的淘汰", "example": "选有 because 证据的原因项，而不是“听起来合理”的项"},
        ],
    },
    "matching": {
        "title": "匹配题的路标、功能和主旨基础",
        "intro": "匹配不是找相同单词，而是确认段落、人物或地点“完成了题目所说的那件事”。",
        "rules": [
            {"signal": "人名、地名、年份、数字、专有名词", "meaning": "这些是独特路标，适合快速缩小位置", "action": "先定位，再读完整句或完整信息块验证", "example": "2018 只出现一次，可先找到候选段"},
            {"signal": "because / therefore / due to", "meaning": "这里通常在解释原因或结果", "action": "题目若找 reason，必须验证因果关系完整", "example": "because it was cheaper = 选择它的原因"},
            {"signal": "for example / such as / including", "meaning": "这里通常是例子，不一定是整段主旨", "action": "信息匹配可用例子；标题匹配不能只凭例子", "example": "段落举苹果例子，主旨可能是健康饮食"},
            {"signal": "but / however / instead / yet", "meaning": "转折后常放作者真正重点或人物最终态度", "action": "至少读到转折后一句再概括", "example": "先说方便，but 后说太贵：最终重点是价格问题"},
            {"signal": "段落反复出现同一概念的不同说法", "meaning": "重复概念比醒目的单个词更接近主旨", "action": "用 5–8 个字写段落功能标签", "example": "省时、快速、效率提高 → “节省时间”"},
            {"signal": "this / they / such a method", "meaning": "代词可能把证据连接到前一句", "action": "向前追到代词真正指代的对象", "example": "This problem 指上一句的交通拥堵"},
            {"signal": "选项是否允许重复", "meaning": "复用规则会改变排除方式", "action": "做题前圈出 may be used more than once 等说明", "example": "可重复时，A 已用过仍能再选 A"},
            {"signal": "题目是否按文章顺序", "meaning": "不同匹配子题型的顺序规律不同", "action": "只在明确有顺序时利用上一题位置，否则全篇查找", "example": "句子结尾通常顺序；标题匹配按段落逐段做"},
        ],
    },
    "completion": {
        "title": "填空与简答必学：看空格前后判断词性",
        "intro": "先看空格左边和右边，预测“需要什么词性、单数还是复数、要哪类信息”，再去原文找词。词性只能缩小候选，最终答案还必须同时符合原文意思、词数和拼写。",
        "rules": [
            {"signal": "a / an + ____ + 谓语、介词或句号", "meaning": "通常缺单数可数名词或以名词为中心的短语", "action": "找一个可以数、单数形式的事物名称", "example": "A ____ is provided. → locker"},
            {"signal": "a / an + ____ + 名词", "meaning": "空格通常修饰后面的名词，常填形容词或名词修饰语", "action": "先问“什么样的这个名词”，再用原文意思确认", "example": "a ____ service → free service；答案 free 是形容词"},
            {"signal": "the / this / that / my / their + ____ + 谓语", "meaning": "空格通常是名词或名词短语，充当主语", "action": "看后面动词单复数，决定名词单复数", "example": "The ____ opens at 9. → centre"},
            {"signal": "____ + 名词", "meaning": "空格通常是形容词或名词修饰语", "action": "问“什么样的/哪一种名词”，不要再填完整句子", "example": "____ tickets → discounted tickets"},
            {"signal": "can / must / should / will + ____", "meaning": "情态动词后面要动词原形", "action": "只找动作原形，不填 -ed、-ing 或第三人称 -s", "example": "Visitors must ____ online. → register"},
            {"signal": "to + ____", "meaning": "普通不定式 to 后填动词原形；但介词 to 后填名词或 -ing", "action": "看 to 前是否是 key/solution/way/approach 等固定搭配", "example": "to book → 动词；the key to reducing waste → reducing"},
            {"signal": "am / is / are / was / were + ____", "meaning": "可能是形容词、名词补语、过去分词或 -ing，不能只凭 be 动词定词性", "action": "根据意思判断是状态、身份、被动动作还是进行动作", "example": "rooms are available；office is located；staff are working"},
            {"signal": "in / on / at / by / with / for / from / after / before + ____", "meaning": "介词后通常接名词、名词短语、代词或动名词 -ing", "action": "优先找地点、时间、方式、对象等名词信息", "example": "by ____ → bus；after booking online → booking"},
            {"signal": "及物动词 + ____", "meaning": "空格通常是动作承受者，即名词或名词短语", "action": "问“动词什么”，找宾语", "example": "receive a ____ → receive a certificate"},
            {"signal": "____ + 完整谓语动词", "meaning": "空格通常充当主语，需要名词或名词短语", "action": "利用谓语单复数反推答案形式", "example": "____ are available. → lockers；____ is available. → parking"},
            {"signal": "数字 + ____", "meaning": "通常缺复数可数名词或计量单位；数字 1 后通常单数", "action": "检查单位、名词和复数 -s 是否完整", "example": "three ____ → days；1 kilometre"},
            {"signal": "many / few / several + ____；much / little + ____", "meaning": "前一组接复数可数名词，后一组接不可数名词", "action": "先判断答案能不能数，再选单复数形式", "example": "many visitors；much information"},
            {"signal": "each / every + ____", "meaning": "后面通常接单数可数名词", "action": "即使整体人数很多，也写单数形式", "example": "every ____ → participant"},
            {"signal": "A and / or ____", "meaning": "并列两边通常词性、形式和信息层级一致", "action": "照着另一边的结构寻找同类答案", "example": "books and ____ → online videos；cheap and ____ → convenient"},
            {"signal": "more / less / -er than / as ... as", "meaning": "空格处可能是形容词、副词、数量或比较对象", "action": "先看比较的是性质、动作还是数量，再确定答案类型", "example": "more ____ than before → visitors；is ____ than A → cheaper"},
            {"signal": "表格、笔记、流程图中句子语法不完整", "meaning": "这类版式常省略冠词和动词，不能只靠一句语法", "action": "同时看标题、行列、箭头和相邻答案的平行结构", "example": "表头 Price 决定空格填 £12，而不是 ticket"},
            {"signal": "预测词性后找到多个候选词", "meaning": "词性只负责筛选，不能单独证明答案", "action": "再查意思、原文证据、答案边界、词数和拼写", "example": "两个名词都能放入时，只有与题意相符的原文词才是答案"},
        ],
    },
}


COURSE_FOUNDATION_ADDITIONS: dict[str, list[dict[str, str]]] = {
    "true_false_not_given": [
        {"signal": "题目要求 TRUE / FALSE / NOT GIVEN", "meaning": "判断的是可核对的事实信息，不是作者喜不喜欢", "action": "把题干改写成“原文是否确认这件事”，不要寻找态度词", "example": "The centre opened in May. → 核对开业月份，这是事实判断"},
        {"signal": "题干中的专有名词、数字或罕见名词", "meaning": "这些词适合定位，但不能直接决定答案", "action": "用它找到原文位置，再比较完整句意", "example": "题干含 Green Hall，先找到 Green Hall，再核对开放对象"},
        {"signal": "题干和原文使用不同词：buy / purchase、start / begin", "meaning": "这是同义改写，不是没找到信息", "action": "把动作翻成最简单中文，再比较意思", "example": "purchased tickets = bought tickets，所以不能因单词不同选 NG"},
        {"signal": "题干多出 only / exactly / at least / no more than", "meaning": "新增限定词会改变事实范围", "action": "逐个核对数字边界和限制，少核对一个词都不能作答", "example": "原文 up to 20，题目 exactly 20：意思不同"},
        {"signal": "原文与题干时态不同", "meaning": "过去、现在和计划中的事情不能混为一谈", "action": "在两边分别写“过去/现在/未来”后再比较", "example": "will close next year ≠ has already closed"},
        {"signal": "题干加入 because / leads to / results in", "meaning": "题干在主张因果关系，而原文可能只说两件事同时发生", "action": "必须找到明确原因或结果连接，不能自己推断", "example": "下雨和人数减少同时出现，不等于下雨导致人数减少"},
        {"signal": "比较级的对象或方向被交换", "meaning": "比较事实可能被说反", "action": "写成 A > B 或 A < B，再判断 TRUE/FALSE", "example": "A is older than B；题目 B is older than A → FALSE"},
        {"signal": "原文没有提到题干中的原因、目的或评价", "meaning": "缺少关系证据，不代表关系相反", "action": "确认全文相关位置都未说明后选 NOT GIVEN", "example": "原文说课程取消，没说因为费用高 → 原因是 NG"},
        {"signal": "证据跨两句，并出现 this / it / they", "meaning": "第二句可能通过代词补完整题干信息", "action": "向前追代词，连读前后句后再判断", "example": "The scheme began in June. It served older residents. → it 指 scheme"},
    ],
    "yes_no_not_given": [
        {"signal": "题目要求 YES / NO / NOT GIVEN", "meaning": "判断的是作者或指定人物的观点、主张和评价", "action": "先在题干写“谁认为”，再寻找这个人的态度", "example": "The writer believes... 必须核对 writer，不是文中任一专家"},
        {"signal": "According to X / X argues / the writer suggests", "meaning": "这些词明确指定观点主人", "action": "把 X 的名字写在证据句旁，防止串人", "example": "Dr Lee argues A；writer reports it，不等于 writer 同意 A"},
        {"signal": "supports / favours / beneficial / should / best", "meaning": "通常表示赞成、推荐或正面评价", "action": "确认态度属于指定人物且针对同一主张，再考虑 YES", "example": "The writer calls the plan beneficial → 对“作者支持计划”是 YES"},
        {"signal": "rejects / doubts / harmful / unrealistic / should not", "meaning": "通常表示反对、怀疑或负面评价", "action": "确认否定对象后再考虑 NO", "example": "The author says the proposal is unrealistic → 作者不赞成"},
        {"signal": "reports / describes / notes / mentions", "meaning": "这些词可能只是中性转述，不表示赞成", "action": "继续寻找评价词；只有介绍没有态度时不要选 YES", "example": "The writer mentions a proposal，不代表 supports the proposal"},
        {"signal": "could / may / ought to / must", "meaning": "建议强度和确定程度不同", "action": "把“可能、应该、必须”分别核对，不能当成同一态度", "example": "could help ≠ must be adopted"},
        {"signal": "although / while / but / however", "meaning": "人物可能先承认一部分，转折后才给最终立场", "action": "读完转折后的完整句再判态度", "example": "Although useful, it is too costly → 最终并非完全支持"},
        {"signal": "作者用反问、讽刺或谨慎措辞", "meaning": "态度可能没有直接使用 agree/disagree", "action": "只按可证明的语气和上下文判断，不凭个人感觉放大", "example": "It is difficult to see how this could work → 对可行性持怀疑"},
        {"signal": "文中谈了主题，却没有指定人物的立场", "meaning": "有相关内容仍可能是 NOT GIVEN", "action": "问“这个人有没有明确赞成或反对”，两者都没有就选 NG", "example": "介绍免费公交的成本，但作者未评价是否应该实施 → NG"},
    ],
    "multiple_choice_single": [
        {"signal": "题干问 main idea / main purpose", "meaning": "答案必须概括整段或整篇功能，不能只说细节", "action": "先用一句话概括大部分内容，再匹配选项", "example": "整段解释新制度如何运作，某个日期只是细节"},
        {"signal": "题干问 Why / reason", "meaning": "需要原因证据，不是结果、时间或背景", "action": "寻找 because、due to 或同义因果句", "example": "活动改到早上 because rooms are quieter → 原因是更安静"},
        {"signal": "题干问 purpose / aim / in order to", "meaning": "需要“做这件事想达到什么”，不一定是后来结果", "action": "区分目的和实际结果", "example": "计划旨在 reduce traffic；后来省钱是结果，不是原目的"},
        {"signal": "题干含 NOT / EXCEPT / least likely", "meaning": "需要选错误项或例外项，作答方向与普通题相反", "action": "把否定词框住，给每项标“文中支持/不支持”", "example": "Which is NOT provided? 要选没有提供的服务"},
        {"signal": "细节题通常跟随文章顺序", "meaning": "上一题证据附近可帮助缩小下一题区域", "action": "从上一题后面继续找，但仍允许少量回跳", "example": "第 5 题在第二段，第 6 题通常从其后继续定位"},
        {"signal": "选项把原因和结果对调", "meaning": "词都在原文里，逻辑方向却错误", "action": "画箭头“原因 → 结果”再核对", "example": "原文：费用高导致退出；选项：退出导致费用高 → 错"},
        {"signal": "选项改变人群、地点或时间", "meaning": "主体或条件一变，选项整体失效", "action": "把选项拆成谁、何时、何地、做什么逐格核对", "example": "原文 adults on weekdays；选项 children at weekends → 错"},
        {"signal": "选项使用 stronger / only / completely 等更强说法", "meaning": "正确方向可能被夸大成错误答案", "action": "比较原文程度，原文只有部分支持就排除绝对项", "example": "helps some users ≠ solves the problem completely"},
        {"signal": "四项都读完仍然觉得相似", "meaning": "还没有建立证据表，只是在比较语感", "action": "给每项写支持句位置和错误点，最后选唯一完整成立项", "example": "A 对象错、B 有完整证据、C 范围错、D 没回答问题 → 选 B"},
    ],
    "multiple_choice_multiple": [
        {"signal": "Choose TWO / Choose THREE", "meaning": "答案数量是硬性规则，多一个少一个都错", "action": "在题号旁画固定数量的空框，找到一项勾一框", "example": "Choose TWO：最终必须正好有两个有证据的字母"},
        {"signal": "题干问 which features / reasons / statements", "meaning": "所有正确项必须回答同一种信息类型", "action": "先给答案类型贴标签，再检查每个选项是否属于该类型", "example": "问 reasons，描述活动结果的选项不能入选"},
        {"signal": "一个选项已有证据", "meaning": "它只能证明自己，不能证明相邻或相似选项", "action": "每个候选旁分别写证据位置", "example": "原文说 bring water，只能证明 water，不能顺带证明 food"},
        {"signal": "正确信息分散在多个段落", "meaning": "多选答案不一定连续出现", "action": "阅读时保留 A–F 核对表，跨段累计证据", "example": "A 在第二段、D 在第四段，两项都可正确"},
        {"signal": "两个选项意思几乎相同", "meaning": "可能一个更精确，也可能题目确实允许分别成立", "action": "不要按“相似所以只能选一个”猜测，分别检查完整证据", "example": "cheap 与 free 不是同义；原文 free 不能证明 merely cheap 是题目所需精确答案"},
        {"signal": "选项满足动作但不满足限制条件", "meaning": "部分匹配仍然不能入选", "action": "同时核对对象、动作、时间和资格", "example": "有电脑课程，但仅限会员；题干问 everyone → 不选"},
        {"signal": "题干包含 NOT / which are NOT mentioned", "meaning": "要选缺失或不符合的多项", "action": "先把所有有证据项划掉，再按要求数量选剩余项", "example": "Choose TWO NOT offered → 选择未提供的两项"},
        {"signal": "选项顺序与原文顺序不同", "meaning": "不能按 A、B、C 顺序期待证据出现", "action": "以文章内容顺序阅读，以选项表记录命中", "example": "原文先证明 E，再证明 B，是正常情况"},
        {"signal": "找到规定数量后想立刻停止", "meaning": "前面可能误选了部分正确项", "action": "快速核对剩余选项并回查已选项的全部条件", "example": "已选 A、C 后发现 D 有直接证据，而 C 只有半句支持，应改为 A、D"},
    ],
    "matching_information": [
        {"signal": "题目要求 a reason / cause", "meaning": "目标是解释“为什么”，不是只提到同一主题", "action": "寻找明确因果句，并确认原因对象一致", "example": "B 段说 because rent increased，才是搬迁原因"},
        {"signal": "题目要求 an example / illustration", "meaning": "目标是具体实例，而不是普遍观点", "action": "找真实人、事件、数字或 for example 后内容", "example": "“一位 70 岁居民每天使用服务”是具体例子"},
        {"signal": "题目要求 a comparison / contrast", "meaning": "段落必须同时比较两个对象或两个时期", "action": "确认文中出现比较双方和差异", "example": "A 比 B 便宜才构成比较；只介绍 A 不够"},
        {"signal": "题目要求 a problem / difficulty", "meaning": "目标是困难、障碍或负面后果", "action": "寻找 problem、lack、unable、too costly 等表达", "example": "缺少员工导致无法延长开放时间 → 问题"},
        {"signal": "题目要求 a solution / response", "meaning": "目标是为问题采取的办法", "action": "找 therefore、to solve this、responded by 等动作", "example": "为解决排队，中心增加线上预约 → 解决办法"},
        {"signal": "题目要求 a prediction / future possibility", "meaning": "需要未来判断，不是当前事实", "action": "寻找 will、likely、expected、may in future", "example": "The service is expected to expand → 未来预测"},
        {"signal": "题目要求 an opinion / criticism", "meaning": "需要某人的评价或态度", "action": "同时找观点主人和态度词", "example": "Lee considers the policy unfair → Lee 的批评"},
        {"signal": "题目要求 a change / development", "meaning": "段落需显示前后状态不同", "action": "寻找 previously/now、from/to、increased/decreased", "example": "原来每周一次，现在每天开放 → 变化"},
        {"signal": "一个信息由相邻两句共同完成", "meaning": "只读含关键词的一句可能看不到完整功能", "action": "候选位置前后各读一句，追踪代词和因果", "example": "第一句提方案，第二句 This reduced waiting times，合起来才是效果"},
    ],
    "matching_headings": [
        {"signal": "段落中多个句子围绕同一动作或结果", "meaning": "重复概念通常就是主旨核心", "action": "用“对象 + 主要发生什么”写一句段意", "example": "材料变轻、速度提高、用途扩大 → 新材料带来的改变"},
        {"signal": "首句给主题，后文一直解释或展开", "meaning": "首句可能就是主题句", "action": "用后面句子验证首句是否能罩住全段", "example": "首句说课程优势，后文全是不同优势 → 可据此概括"},
        {"signal": "首句是问题、历史背景或旧观点", "meaning": "开头不一定代表作者最终重点", "action": "继续读到转折和结尾，再写段意", "example": "过去方法很慢；however 后介绍新方法 → 标题应选新方法"},
        {"signal": "段落出现 for example、数字或一个人名故事", "meaning": "这是支撑主旨的小证据", "action": "把例子上升一层，问它证明什么", "example": "某公司节省 30% 时间 → 证明新系统提高效率"},
        {"signal": "段落结构是 problem → solution", "meaning": "标题可能概括解决办法或问题被解决", "action": "分别写问题和办法，看哪部分占主要篇幅", "example": "先一句说拥堵，后四句讲预约制度 → 主旨偏解决办法"},
        {"signal": "段落结构是 old view → but → new view", "meaning": "转折后的新观点通常更重要", "action": "标题优先覆盖新观点和变化", "example": "曾认为老人不用网络，但调查显示使用率很高 → 观念被改变"},
        {"signal": "一个标题只覆盖段落中的一个名词或一句话", "meaning": "标题范围太窄", "action": "检查它能否解释至少大部分句子", "example": "段落讲多种交通改革，“自行车停车位”只是一项细节"},
        {"signal": "一个标题非常宽泛，几乎每段都能用", "meaning": "标题范围太大，缺少本段独特点", "action": "寻找带有本段核心动作、原因或结果的更具体标题", "example": "“城市生活”太宽；“夜间交通改善”更准确"},
        {"signal": "标题选项有多余项且词汇与段落重复", "meaning": "多余标题故意用同词诱导", "action": "先用自己的话概括，再对照选项，不按同词选择", "example": "段落出现 cost，但主旨是服务扩展；“费用问题”是干扰项"},
    ],
    "matching_features": [
        {"signal": "选项是一组人物、理论、产品或类别", "meaning": "每个字母代表不同对象，需要先建立对应表", "action": "在草稿写 A=谁、B=谁、C=谁", "example": "A=Mia，B=Noah，避免后面记反"},
        {"signal": "对象第一次出现并带有动作或观点", "meaning": "这是对象档案的第一条特征", "action": "立即记录“对象—特点—限制”", "example": "Mia—喜欢线上课—因为时间灵活"},
        {"signal": "两个对象讨论同一主题", "meaning": "主题相同不代表特点相同", "action": "圈出两者真正不同的态度、原因或条件", "example": "都谈网络；A 赞成便利，B 担心隐私"},
        {"signal": "题干使用 ability to / preference for / concern about", "meaning": "它可能改写原文中的 can、prefer、worry", "action": "把抽象名词还原成简单动词后匹配", "example": "concern about cost = worries that it is expensive"},
        {"signal": "说明 letters may be used more than once", "meaning": "同一对象可拥有多个特征", "action": "不要因为某字母已用过就排除", "example": "Mia 既重视时间灵活，也喜欢居家学习，可选两次"},
        {"signal": "题目描述顺序与对象出现顺序不一致", "meaning": "这类题不一定按文章顺序逐题定位", "action": "先完成对象档案，再从题目反查档案", "example": "第 1 题可能对应最后出现的 C"},
        {"signal": "题干同时含行为和限制条件", "meaning": "两个部分必须属于同一对象", "action": "逐项核对动作、对象和限制，不拼接两个人的信息", "example": "提供课程且仅限儿童：不能把 A 的课程和 B 的儿童限制拼起来"},
        {"signal": "对象先赞成，后面出现 not / rarely / no longer", "meaning": "否定可能改变最终特征", "action": "把否定词连同后面内容记入档案", "example": "used to prefer classes but no longer does → 现在不偏好课堂"},
        {"signal": "完成若干明显匹配后仍剩两个相似对象", "meaning": "可以用已确认差异和剩余条件排除", "action": "先核实已做答案，再用排除法处理最后题目", "example": "A 已证实重价格，剩余“重位置”由 B 的直接证据确认"},
    ],
    "matching_sentence_endings": [
        {"signal": "句子前半以 to / because / although / so that 结束", "meaning": "连接词预告后半需要的语法和逻辑", "action": "先写“目的/原因/让步/结果”，再看结尾", "example": "in order to ... → 后面必须表达目的动作"},
        {"signal": "主句缺宾语、补语或完整从句", "meaning": "不同空缺需要不同结构的结尾", "action": "判断前半句语法缺什么，再初步筛选", "example": "The study showed that ... → 需要完整陈述内容"},
        {"signal": "题目通常按原文顺序出现", "meaning": "后一道题证据多在前一道之后", "action": "按题号顺序定位，减少重复全文搜索", "example": "第 20 题在第三段，第 21 题从第三段后半继续"},
        {"signal": "某结尾接上后主谓、时态或单复数不通", "meaning": "即使含原文词也不可能正确", "action": "先读成完整句，用语法排除", "example": "主语单数却接 have completed，需检查是否结构错误"},
        {"signal": "结尾含 it / they / this group / these", "meaning": "代词必须有明确且数量一致的先行词", "action": "把代词替换成它指代的名词后朗读", "example": "they 不能指单数 the centre"},
        {"signal": "两个结尾语法都正确", "meaning": "真正区别在原文意义和逻辑关系", "action": "分别找原文证据，不能只凭顺口", "example": "两个动词短语都能接 to，只有 serve workers 有证据"},
        {"signal": "结尾照抄原文词但改变因果或对象", "meaning": "同词结尾可能是强干扰项", "action": "检查完整句是谁做什么、为什么", "example": "原文 workers saved time；结尾写 company saved workers → 对象关系错误"},
        {"signal": "前半和结尾各自正确，但不属于同一句原文关系", "meaning": "两个真实信息被错误拼接", "action": "要求同一证据区域能够完整支持连接后的句子", "example": "便宜是真的、周末开放也是真的，但原文没说因便宜才周末开放"},
        {"signal": "所有题做完后形成完整句子", "meaning": "最终复核必须同时过语法和证据两关", "action": "逐句朗读，并在原文指出支持位置", "example": "读起来通顺但找不到完整证据，仍需重做"},
    ],
    "matching_names": [
        {"signal": "新姓名、姓氏或职业称谓出现", "meaning": "说话者范围可能切换", "action": "从该位置读到下一个人物切换点，建立人物卡", "example": "Dr Lee 后面的观点先归 Lee，直到出现 Professor Khan"},
        {"signal": "he / she / they / the researcher / the director", "meaning": "代词或职位可能继续指上一位人物", "action": "向前找最近且逻辑一致的人名", "example": "She also recommends... 中 she 继续指前句 Anna"},
        {"signal": "argues / claims / admits / warns / recommends", "meaning": "报告动词说明观点类型和态度强度", "action": "把动词和观点内容一起记录", "example": "warns that costs may rise → 对成本上升发出警告"},
        {"signal": "agrees / supports 与 rejects / disputes", "meaning": "可直接区分赞同和反对", "action": "核对人物反对的是哪一个具体主张", "example": "Lee rejects the timetable，不代表反对整个项目"},
        {"signal": "although / but / nevertheless", "meaning": "人物最终重点常在转折后", "action": "人物卡记录转折后的最终立场", "example": "喜欢设计，但认为价格决定选择 → 重点是价格"},
        {"signal": "多个人都谈 cost / access / quality", "meaning": "共同话题不能区分人物", "action": "记录每个人对话题的不同评价或原因", "example": "A 认为费用合理，B 认为费用阻碍参加"},
        {"signal": "同一人物在后文再次出现", "meaning": "人物观点可能分散在多个段落", "action": "继续补充原人物卡，不只看第一次出现", "example": "Lee 在第五段补充对线上服务的看法"},
        {"signal": "说明人物字母可重复使用", "meaning": "同一人可对应多道观点题", "action": "按证据重复选择，不做强制一人一题", "example": "Anna 既重价格又重交通，可连续两题选 Anna"},
        {"signal": "X says that Y believes...", "meaning": "句中可能同时有转述者和真正观点主人", "action": "问“这是谁的看法”，不要把转述动作当成赞同", "example": "The writer reports Lee's concern → concern 属于 Lee，不一定属于 writer"},
    ],
    "matching_places": [
        {"signal": "新地点名、区域名或设施名出现", "meaning": "新的地点信息块开始", "action": "从地点名读到下一个地点，建立地点卡", "example": "North Hall：电脑、会员、工作日开放"},
        {"signal": "next to / opposite / behind / on the first floor", "meaning": "这些词说明地点位置，不一定说明功能", "action": "把“在哪里”和“做什么”分开记录", "example": "opposite the café 是位置，offers printing 才是功能"},
        {"signal": "offers / provides / contains / is used for", "meaning": "后面通常是设施或服务功能", "action": "在地点卡的“功能”栏记录", "example": "East Room provides quiet study spaces"},
        {"signal": "for members / open to children / available to all", "meaning": "后面说明谁可以使用", "action": "把使用对象作为独立条件核对", "example": "members only 不符合 available to everyone"},
        {"signal": "weekdays / after 6 pm / during summer", "meaning": "开放时间可能决定最终匹配", "action": "功能相同时用时间限制区分地点", "example": "两个房间都有电脑，只有 B 周末开放"},
        {"signal": "free / fee / deposit / booking required", "meaning": "费用和预约条件也是地点特征", "action": "不要只记服务，要把使用条件一起写入地点卡", "example": "免费场地与需要 £10 deposit 的场地不能混"},
        {"signal": "两个地点提供相同设施", "meaning": "设施名本身不足以决定答案", "action": "继续比较对象、时间、费用和具体位置", "example": "都有打印机，但只有 South Hub 对公众开放"},
        {"signal": "except / not available / temporarily closed", "meaning": "否定或例外会取消看似匹配的服务", "action": "在地点卡用叉号记录不可用条件", "example": "normally open, except Sundays → 星期日不能选该地点"},
        {"signal": "同一地点在不同句分别说明位置与功能", "meaning": "证据可能跨句，不能只看地点名旁第一句", "action": "读完整地点信息块，合并成“位置—功能—对象—限制”表", "example": "第一句说楼层，第二句才说儿童活动，需合并判断"},
    ],
}


COURSE_ANSWER_FORMS: dict[str, str] = {
    "true_false_not_given": "答案只能是 TRUE、FALSE 或 NOT GIVEN；先确认原文是否完整谈到，再判断同义或相反。",
    "yes_no_not_given": "答案只能是 YES、NO 或 NOT GIVEN；判断的是指定人物的观点，不是事实是否存在。",
    "multiple_choice_single": "只选一个字母；该选项必须完整回答题干，不能只是原文提到过。",
    "multiple_choice_multiple": "按题目要求选固定数量的字母；每个字母都需要各自的直接证据。",
    "matching_information": "填写段落字母；答案表示哪一段完整包含所问信息功能。",
    "matching_headings": "填写标题编号；答案要覆盖整段主旨，不能只覆盖一个例子。",
    "matching_features": "填写对象字母；先确认是否允许同一对象重复使用。",
    "matching_sentence_endings": "填写结尾选项字母；连接后语法和原文意义都必须成立。",
    "matching_names": "填写人物字母；观点、行为和限定条件必须属于同一个人。",
    "matching_places": "填写地点字母；位置、功能、开放对象和时间限制都要一致。",
    "sentence_completion": "常见答案是名词/名词短语、数字、形容词或动词；具体形式由空格前后语法决定。",
    "summary_completion": "常见答案是名词、形容词、动词或数字；既要看单句语法，也要看整段摘要逻辑。",
    "note_completion": "常用压缩后的名词短语；同一层级项目通常保持相同词性和信息类型。",
    "table_completion": "答案类型主要由行标题与列标题的交叉位置决定，常见为名称、数字、日期、价格或单位。",
    "flow_chart_completion": "常见答案是动作、材料或结果；先看箭头，再确定需填动词还是名词。",
    "diagram_label_completion": "通常填部件名、材料名或方向词；名称必须与箭头指向的位置同时正确。",
    "short_answer": "Who 填人，Where 填地点，When 填时间，Why 填原因，How many 填数量；只写最短必要原文信息。",
}


COURSE_DECISION_GUIDES: dict[str, list[dict[str, str]]] = {
    "true_false_not_given": [
        {"signal": "题干是原文完整同义改写", "meaning": "对象、时间、范围和关系都一致", "action": "选 TRUE", "example": "began in 2010 = started in 2010"},
        {"signal": "原文明说相反方向", "meaning": "不是缺信息，而是有反证", "action": "选 FALSE", "example": "原文 cheaper，题目 more expensive"},
        {"signal": "原文提到对象但没说题干关系", "meaning": "证据不足", "action": "选 NOT GIVEN", "example": "说课程开设，没说课程是否受欢迎"},
        {"signal": "some / may 被换成 all / must", "meaning": "范围或强度被扩大", "action": "通常判 FALSE，但先核对同一对象和时间", "example": "Some visitors may wait ≠ All visitors must wait"},
    ],
    "yes_no_not_given": [
        {"signal": "指定人物明确赞成同一主张", "meaning": "观点一致", "action": "选 YES", "example": "writer supports = writer believes it is beneficial"},
        {"signal": "指定人物明确批评或拒绝", "meaning": "观点相反", "action": "选 NO", "example": "writer calls the plan impractical"},
        {"signal": "文章介绍观点但指定人物没表态", "meaning": "没有态度证据", "action": "选 NOT GIVEN", "example": "只说 some experts believe..."},
        {"signal": "同段有作者和专家两种声音", "meaning": "最容易认错说话人", "action": "先在人名旁标观点，再作答", "example": "Dr Li supports；writer remains uncertain"},
    ],
    "multiple_choice_single": [
        {"signal": "题目问 Why，原文有 because / due to", "meaning": "这里可能是直接原因证据", "action": "比较选项，选完整改写该原因的一项", "example": "because it was quieter → fewer people"},
        {"signal": "某选项大量出现原文词", "meaning": "可能只是同词诱饵", "action": "问它是否真的回答题干焦点", "example": "出现 ticket，但题目问开放时间"},
        {"signal": "选项一半有证据、一半没有", "meaning": "整项不成立", "action": "立即排除", "example": "更快有证据，更便宜无证据"},
        {"signal": "最后剩两个选项", "meaning": "不能靠语感二选一", "action": "给两项分别找完整证据，选证据更直接者", "example": "只有 B 能由原文整句推出"},
    ],
    "multiple_choice_multiple": [
        {"signal": "Choose TWO / THREE", "meaning": "答案数量固定", "action": "先圈数量，提交前再数一次", "example": "Choose TWO 必须恰好两项"},
        {"signal": "找到第一个正确项", "meaning": "其他项仍需独立验证", "action": "不要把相似项一起选，逐项找证据", "example": "water 有证据不代表 food 也正确"},
        {"signal": "证据分散在不同段", "meaning": "答案不一定集中出现", "action": "保留选项表，随阅读逐项打勾或叉", "example": "A 在第 2 段，D 在第 4 段"},
        {"signal": "选项只符合一部分条件", "meaning": "部分正确仍然错误", "action": "核对对象、动作、限制全部成立", "example": "提供课程，但不对儿童开放"},
    ],
    "matching_information": [
        {"signal": "题目含 a reason / explanation", "meaning": "找因果功能", "action": "寻找 because、therefore 或完整因果改写", "example": "why the centre moved → B 段解释租金上涨"},
        {"signal": "题目含 an example", "meaning": "找具体实例而非笼统观点", "action": "寻找 for example、such as 或具体人事物", "example": "C 段列出一次真实活动"},
        {"signal": "多个段都有相同主题词", "meaning": "关键词不能决定答案", "action": "比较哪段完整执行题目所说的功能", "example": "都谈 transport，只有 D 段作比较"},
        {"signal": "说明可重复使用段落", "meaning": "一段可能回答多题", "action": "不要因已选过就排除", "example": "B 段既有原因又有例子，可对应两题"},
    ],
    "matching_headings": [
        {"signal": "首句只是介绍旧情况", "meaning": "背景不一定是主旨", "action": "继续读转折和结尾，再概括整段", "example": "过去很贵，however 现在新技术降低成本"},
        {"signal": "段中有醒目例子或数字", "meaning": "具体细节可能只是支撑", "action": "问大部分句子共同说明什么", "example": "30% 是例子，主旨是使用量增长"},
        {"signal": "but / however / instead", "meaning": "后面常是重点变化", "action": "把转折后内容写进段落标签", "example": "不是缺资金，而是缺人员"},
        {"signal": "两个标题都相关", "meaning": "一个可能范围太窄或太宽", "action": "选能覆盖大多数句子的标题", "example": "“新材料的影响”优于“一个自行车零件”"},
    ],
    "matching_features": [
        {"signal": "看到对象首次出现", "meaning": "需要建立对象小档案", "action": "记录其观点、行为和限制", "example": "A：重价格；B：重服务"},
        {"signal": "两个对象都谈同一主题", "meaning": "共同主题不是答案，差异才是", "action": "圈出态度或条件的不同", "example": "都谈课程，A 喜欢线上，B 喜欢面授"},
        {"signal": "选项可重复", "meaning": "同一对象可对应多条描述", "action": "按证据作答，不做强制一一配对", "example": "Mia 可同时对应时间灵活和居家学习"},
        {"signal": "题干使用同义改写", "meaning": "不一定出现对象原话", "action": "把题干改写回对象档案的意思", "example": "study at any time = flexible schedule"},
    ],
    "matching_sentence_endings": [
        {"signal": "句子前半暗示原因、目的或结果", "meaning": "先预测逻辑关系可减少候选", "action": "给空位写“原因/目的/结果”", "example": "in order to → 目的"},
        {"signal": "结尾接上后语法不通", "meaning": "该项一定错误", "action": "先用语法快速排除", "example": "to 后不能直接接完整过去式句子"},
        {"signal": "多个结尾语法都通", "meaning": "语法只是第一关", "action": "回原文验证关系和事实", "example": "两项都是动词短语，只有一项有证据"},
        {"signal": "结尾含 it / they / these", "meaning": "代词对象可能不匹配", "action": "明确代词指谁再连接", "example": "they 必须能指向复数主语"},
    ],
    "matching_names": [
        {"signal": "出现新姓名", "meaning": "说话者范围开始或切换", "action": "在姓名旁建立观点卡", "example": "Anna: cost；Ben: location"},
        {"signal": "believes / argues / doubts / recommends", "meaning": "这些词显示态度和观点", "action": "把态度词与后面内容一起记录", "example": "doubts the plan = 对计划不确定"},
        {"signal": "but / although / however", "meaning": "人物最终观点可能在转折后", "action": "记录转折后的结论，不只记前半句", "example": "喜欢位置，但认为价格最重要"},
        {"signal": "同一姓名后来再次出现", "meaning": "人物信息可能分散", "action": "补充同一张观点卡，不新建人物", "example": "第 2 段和第 5 段的 Lee 属于同一人"},
    ],
    "matching_places": [
        {"signal": "大写地点名或地图标签", "meaning": "可快速定位地点信息块", "action": "框出地点名并读到下一个地点", "example": "North Hall 信息读完整"},
        {"signal": "offers / provides / is used for", "meaning": "后面说明地点功能", "action": "把功能写在地点旁", "example": "provides childcare → 托儿服务"},
        {"signal": "only / except / available to", "meaning": "后面是使用限制", "action": "把开放对象和限制一起核对", "example": "members only 不符合 everyone"},
        {"signal": "两个地点都有相似设施", "meaning": "需用时间、对象或位置区分", "action": "比较全部条件，不只看设施名", "example": "都有电脑，但只有 East Room 周末开放"},
    ],
    "sentence_completion": [
        {"signal": "空格前有 a/an，后面没有名词", "meaning": "需要单数可数名词或名词短语", "action": "先预测“一个什么东西”，再定位原文", "example": "given a ____ → certificate"},
        {"signal": "空格后紧跟名词", "meaning": "多半需要形容词或名词修饰语", "action": "先问“什么样的名词”", "example": "____ rooms → quiet rooms"},
        {"signal": "空格前是 must/can/should", "meaning": "需要动词原形", "action": "排除 -ing、-ed、-s 形式", "example": "must ____ → register"},
        {"signal": "找到原文候选词", "meaning": "还没有完成", "action": "放回整句，核对词性、单复数、词数和拼写", "example": "a reusable bottle 语法和两词上限都合格"},
    ],
    "summary_completion": [
        {"signal": "摘要有标题和连续几空", "meaning": "答案多来自原文同一信息区并按顺序", "action": "先读完整摘要，确定主题和起止位置", "example": "摘要讲申请流程，就在原文申请段顺序找"},
        {"signal": "空格前后构成完整句子", "meaning": "可用词性预测答案形状", "action": "按冠词、介词、谓语和并列规则判断", "example": "in ____ rooms → 名词短语；____ rooms → 形容词"},
        {"signal": "first / then / because / however", "meaning": "摘要逻辑连接原文顺序或因果", "action": "利用连接词确认相邻答案关系", "example": "before being kept 对应 first...then"},
        {"signal": "有词库", "meaning": "答案必须从词库选且可能有多余词", "action": "先按词性分组，再按意义逐空排除", "example": "rooms 前只保留形容词候选"},
    ],
    "note_completion": [
        {"signal": "标题、缩进和项目符号", "meaning": "它们表示信息层级和范围", "action": "先确定空格属于哪一个大点", "example": "Facilities 下的空不能填 Fees 信息"},
        {"signal": "同层项目已经有答案", "meaning": "并列项通常词性和信息类型一致", "action": "照着邻项预测答案", "example": "books；____ → 另一个名词 online videos"},
        {"signal": "笔记没有完整句子", "meaning": "语法提示可能被省略", "action": "同时看标题、冒号和上下项目", "example": "Benefits: ____ 可直接填名词短语"},
        {"signal": "找到一整句解释", "meaning": "答案往往只要其中中心词", "action": "按词数留下最短完整原文词", "example": "because it saves a great deal of time → time"},
    ],
    "table_completion": [
        {"signal": "空格位于某一行和某一列", "meaning": "两个表头共同决定答案", "action": "把行名+列名念成一个问题", "example": "Child + Price → 儿童票价是多少"},
        {"signal": "整列是数字、日期或地点", "meaning": "空格应保持同类数据格式", "action": "参考上下单元格预测答案类型", "example": "Price 列已有 £12，空格也应是价格"},
        {"signal": "相邻两行文字很像", "meaning": "容易把答案填到错误行", "action": "每填一格都回看行标题", "example": "不要把 Adult 的 £12 填给 Child"},
        {"signal": "数字旁是否已有单位", "meaning": "决定答案要不要包含单位", "action": "题干已有 kg 就只填数字；没有则按原文和词数保留", "example": "Weight (kg): ____ → 12，不再写 kg"},
    ],
    "flow_chart_completion": [
        {"signal": "箭头和 first/then/finally", "meaning": "答案必须遵守步骤顺序", "action": "从起点沿箭头逐框对应原文", "example": "washed → cut → packed"},
        {"signal": "空框前后都是动作", "meaning": "空格多半也要动作形式", "action": "保持并列形式，检查主动或被动", "example": "is washed → is cut → is packed"},
        {"signal": "框里问 material / result", "meaning": "需要名词而不是动作", "action": "先给每框标“动作/材料/结果”", "example": "produces ____ → a fine powder"},
        {"signal": "原文和图中主被动不同", "meaning": "意思相同但词形可能受题面限制", "action": "以题目现有语法决定空格形式，并遵守原词要求", "example": "workers dry seeds ↔ seeds are dried"},
    ],
    "diagram_label_completion": [
        {"signal": "箭头指上/下/内/外/连接处", "meaning": "空间位置是第一层证据", "action": "先用中文说清箭头位置", "example": "指下方出口，不是上方入口"},
        {"signal": "原文连续列出多个部件", "meaning": "有多个词性都正确的候选", "action": "用方向和相邻部件逐一排除", "example": "upper pipe 与 lower valve 不能互换"},
        {"signal": "图上已有标签", "meaning": "已有词提供关系，也不能重复当答案", "action": "利用已有部件判断缺失部件位置", "example": "入口已标 pipe，空格可能问 valve"},
        {"signal": "部件名前有修饰词", "meaning": "修饰词可能是区分位置所必需", "action": "在词数允许时保留必要方向词", "example": "lower valve 不能只写 valve，若图中有两个 valve"},
    ],
    "short_answer": [
        {"signal": "Who / Where / When", "meaning": "分别需要人、地点、时间", "action": "只抄能直接回答的最短信息", "example": "Where...? → the town library"},
        {"signal": "How many / How much", "meaning": "需要数量、金额或程度", "action": "检查数字与必要单位", "example": "How many days? → three days"},
        {"signal": "Why", "meaning": "需要原因，不是结果或背景", "action": "找 because / due to / so that 对应原因边界", "example": "Why moved? → because rent increased"},
        {"signal": "答案附近有很多修饰语", "meaning": "全部照抄容易超词", "action": "保留中心词和答题必需修饰词，删去解释", "example": "Where...? 写 town library，不写 on Friday"},
    ],
}


# The method page deliberately owns its teaching procedure.  Do not import the
# diagnostic/AI lesson templates here: this catalogue must remain usable with
# every AI provider disabled.
COURSE_OPENINGS: dict[str, dict[str, Any]] = {
    "true_false_not_given": {
        "look": "先看题目是不是要求 TRUE / FALSE / NOT GIVEN。",
        "mark": "圈出人物或事物、动作、时间、数量和 all / some / may / must 等范围词。",
        "say": "我先找原文有没有说完整，再判断同义还是相反。",
        "avoid": "不要一看到相同单词就选 TRUE，也不要因为没看到原词就选 NOT GIVEN。",
        "critical_words": ["对象词", "时间词", "数量和程度词", "否定词", "因果和比较词"],
    },
    "yes_no_not_given": {
        "look": "先确认题目问的是作者、专家还是某位说话者的观点。",
        "mark": "圈出观点主人和 should、best、wrong、doubt、support 等态度词。",
        "say": "这是谁的观点？这个人明确赞成、反对，还是没有表态？",
        "avoid": "文章介绍某个观点，不等于作者同意这个观点。",
        "critical_words": ["观点主人", "态度动词", "评价词", "转折词", "语气强弱词"],
    },
    "multiple_choice_single": {
        "look": "先看题干问 Why、What、How、main purpose，还是含 NOT / EXCEPT。",
        "mark": "圈出问题词、对象、时间、范围和否定词；暂时不要被选项带走。",
        "say": "它真正问什么？我期待看到一个原因、目的、事实还是主旨？",
        "avoid": "选项在原文里出现过，不代表它回答了这个问题。",
        "critical_words": ["问题词", "题干焦点", "否定词", "选项差异词", "原因与结果"],
    },
    "multiple_choice_multiple": {
        "look": "第一眼只找 Choose TWO / THREE，先确定必须选几个。",
        "mark": "画出固定数量的答案框，再圈出所有正确项必须满足的共同条件。",
        "say": "每个选项都要有自己的证据，不能因为相似就一起选。",
        "avoid": "找到一个正确项后，不要顺手选择与它相关但没有独立证据的项。",
        "critical_words": ["选择数量", "共同条件", "NOT / EXCEPT", "选项限制词", "独立证据"],
    },
    "matching_information": {
        "look": "先判断题目要找的是原因、例子、问题、比较、观点还是变化。",
        "mark": "圈功能词，再圈人名、数字、地点和罕见名词作为路标。",
        "say": "我要找的是完成这个信息功能的段落，不是出现同一个词的段落。",
        "avoid": "关键词只负责带路，不能单独决定段落字母。",
        "critical_words": ["信息功能词", "独特路标", "因果词", "举例词", "比较和变化词"],
    },
    "matching_headings": {
        "look": "先遮住标题选项，完整读当前段落。",
        "mark": "圈转折词、反复概念和结尾结论，把人名数字先当作例子。",
        "say": "如果只能用八个字介绍这段，我会说什么？",
        "avoid": "不要把一个醒目例子、数字或首句背景当成整段标题。",
        "critical_words": ["转折词", "重复概念", "段落主语", "核心动作", "结尾结论"],
    },
    "matching_features": {
        "look": "先确认 A、B、C 分别代表人物、理论、产品还是类别。",
        "mark": "在草稿建立对象卡：对象—观点/行为—原因—限制。",
        "say": "共同主题不重要，真正区分这些对象的差异是什么？",
        "avoid": "不要把两个人的动作和限制拼成一个答案。",
        "critical_words": ["对象名称", "观点或行为", "原因", "限制", "复用规则"],
    },
    "matching_sentence_endings": {
        "look": "先读句子前半，不看结尾选项，判断它缺原因、目的、结果还是事实。",
        "mark": "圈连接词、代词、主语和动词形式。",
        "say": "正确结尾必须同时通过语法和原文意思两关。",
        "avoid": "语法接得顺但原文没有这个关系，仍然是错项。",
        "critical_words": ["连接词", "逻辑关系", "代词", "单复数", "原文关系"],
    },
    "matching_names": {
        "look": "先框出所有姓名、姓氏和 he / she / the researcher 等指代。",
        "mark": "给每个人建立观点卡，记录转折后的最终态度。",
        "say": "这句话真正是谁说的？是转述者还是被转述的人？",
        "avoid": "不要只记人名出现的位置，要记他具体赞成、反对或做了什么。",
        "critical_words": ["姓名", "人物指代", "观点动词", "转折", "最终态度"],
    },
    "matching_places": {
        "look": "先框出所有地点名，把每个地点看成一张资料卡。",
        "mark": "资料卡写四栏：位置、功能、使用对象、时间/费用限制。",
        "say": "题目描述的全部条件能否同时落在同一个地点？",
        "avoid": "两个地点都有同一设施时，不能只按设施名匹配。",
        "critical_words": ["地点名", "位置", "功能", "开放对象", "时间和费用限制"],
    },
    "sentence_completion": {
        "look": "先圈词数限制，再看空格左边和右边。",
        "mark": "写下预测：词性、单复数、答案类型，例如“单数名词＋地点”。",
        "say": "先猜空格形状，再找原文词，最后放回整句检查。",
        "avoid": "不要先在文章里乱找相同单词，也不要把词数上限当成必须写满。",
        "critical_words": ["词数限制", "冠词和介词", "空格后名词", "谓语单复数", "并列结构"],
    },
    "summary_completion": {
        "look": "先读摘要标题、首句和尾句，确定它在讲哪一段内容。",
        "mark": "圈连接词和每个空格的词性；给词库时先按词性分类。",
        "say": "相邻空格通常沿原文同一信息区顺序前进。",
        "avoid": "不要每个空格单独全文搜索；前一空会告诉你后一空的位置。",
        "critical_words": ["摘要主题", "连接词", "空格词性", "顺序线索", "词库词形"],
    },
    "note_completion": {
        "look": "先看标题、缩进、冒号和项目符号，确认空格属于哪一层。",
        "mark": "圈同层已有项目，预测空格要填同类信息和相同词性。",
        "say": "我要填的是这个标题下面的原因、例子、材料还是结果？",
        "avoid": "笔记常省略语法词，不能只靠空格旁一个词判断。",
        "critical_words": ["标题", "信息层级", "同层项目", "冒号后的类别", "中心词"],
    },
    "table_completion": {
        "look": "把空格所在的行标题和列标题合成一个中文小问题。",
        "mark": "圈上下单元格的数据类型，并检查题目是否已经给了单位。",
        "say": "答案必须同时符合这一行和这一列。",
        "avoid": "不要把相邻行的正确数字填进错误的人群、日期或项目。",
        "critical_words": ["行标题", "列标题", "单位", "比较对象", "相邻行差异"],
    },
    "flow_chart_completion": {
        "look": "先找起点、终点和箭头方向，再看每个框是动作、材料还是结果。",
        "mark": "圈 first、then、after、finally 及主动/被动形式。",
        "say": "我沿箭头走，一次只对应原文中的一步。",
        "avoid": "不要把动作产生的结果误当成下一步动作。",
        "critical_words": ["箭头", "顺序词", "动作", "材料", "结果和主被动"],
    },
    "diagram_label_completion": {
        "look": "先用中文说箭头指向上、下、内、外、入口还是连接处。",
        "mark": "圈图上已有标签和原文方向词，排除已经标出的部件。",
        "say": "名称在原文出现还不够，空间位置也必须对。",
        "avoid": "不要按文章列出部件的顺序，直接假定等于图上的空间顺序。",
        "critical_words": ["箭头位置", "已有标签", "方向词", "相邻部件", "必要修饰词"],
    },
    "short_answer": {
        "look": "先圈 Who、Where、When、Why、How many 和词数上限。",
        "mark": "在题旁写答案类型：人、地点、时间、原因或数量。",
        "say": "问题问什么，我只抄能直接回答的最短原文信息。",
        "avoid": "不要把整句原文搬过来，也不要加入自己的解释。",
        "critical_words": ["问题词", "词数限制", "答案中心词", "必要修饰词", "单位"],
    },
}


FAMILY_EXECUTION_STEPS: dict[str, list[dict[str, str]]] = {
    "judgement": [
        {"id": "instructions", "title": "读清答案规则", "action": "确认是事实判断 TRUE/FALSE，还是观点判断 YES/NO，并确认第三项是 NOT GIVEN。", "why": "事实和观点的证据主人不同，开头认错会导致整组都错。", "example": "writer believes 问作者观点；opened in May 问事实。"},
        {"id": "skeleton", "title": "把题干缩成骨架", "action": "只保留谁/什么、做什么、时间、数量、程度和因果关系。", "why": "修饰词太多时，骨架能暴露真正需要核对的主张。", "example": "All members always pay online → members / pay online / all / always。"},
        {"id": "anchors", "title": "选择定位路标", "action": "优先用人名、地点、数字、罕见名词定位，同时准备它们的同义表达。", "why": "普通词出现太多；路标只负责缩小位置。", "example": "purchase 可能改写为 buy，不能只扫描 purchase。"},
        {"id": "locate", "title": "找到证据区", "action": "找到候选句后连读前后各一句，追踪 this / it / they 指向。", "why": "判断证据经常跨句，单读命中关键词的一句容易缺主语或原因。", "example": "It served older residents 中 it 需要回前句找所指项目。"},
        {"id": "existence", "title": "先判原文说没说完整", "action": "逐格核对对象、动作和题干所问关系是否都出现。缺少关键关系才考虑 NOT GIVEN。", "why": "NOT GIVEN 是证据不足，不是没有看到相同单词。", "example": "原文说课程取消，但没说因为费用高：费用原因是 NG。"},
        {"id": "relationship", "title": "再判一致还是相反", "action": "信息完整出现后，比较动作方向、因果、比较对象和态度。", "why": "只有原文明说相反，才能选 FALSE/NO。", "example": "原文 cheaper，题目 more expensive：有明确反证。"},
        {"id": "qualifiers", "title": "逐个核对小词", "action": "检查 some/all、may/must、often/always、before/after、more/less 和否定词。", "why": "判断题最常把大方向保留，只偷偷改变范围或程度。", "example": "some 不能证明 all；may 不等于 must。"},
        {"id": "source", "title": "确认说话者", "action": "观点题把态度写在对应人物名旁；转述一个观点不等于赞成。", "why": "同一段常有专家和作者两种声音。", "example": "Dr Lee 支持，作者称其 unrealistic：作者态度是反对。"},
        {"id": "answer", "title": "写答案并说理由", "action": "在心里完成一句话：我选___，因为原文___。", "why": "说不出证据关系，说明仍在凭感觉。", "example": "选 FALSE，因为原文 some，而题干 all，范围相反。"},
        {"id": "check", "title": "十秒复核", "action": "再看一次对象、时间、范围和证据是否来自文章而非常识。", "why": "最后一次小词检查常能救回粗心丢分。", "example": "不要把对现实合理的推测当成文章事实。"},
    ],
    "choice": [
        {"id": "instructions", "title": "确认选几个和答题方向", "action": "圈 Choose ONE/TWO/THREE 以及 NOT/EXCEPT。", "why": "数量和否定方向是硬规则，错一个字就会整题失分。", "example": "Which is NOT provided? 要找未提供项。"},
        {"id": "focus", "title": "翻译题干焦点", "action": "把题干改成中文小问题：问原因、目的、主旨、事实还是观点？", "why": "选项会用原文词诱导你回答另一个问题。", "example": "Why moved? 只找搬迁原因，不选搬迁后的结果。"},
        {"id": "predict", "title": "看选项前先预测", "action": "用几个中文词写出可能的答案方向。", "why": "先预测能让你用题干控制选项，而不是被选项带着走。", "example": "问时间改变原因，预测要找 because 后的信息。"},
        {"id": "options", "title": "拆开每个选项", "action": "用斜线拆成对象/动作/原因/时间/范围，圈出选项之间真正不同的词。", "why": "长选项常前半正确、后半错误。", "example": "更快 / 而且更便宜：两部分都要有证据。"},
        {"id": "locate", "title": "用题干定位证据区", "action": "先用题干路标和同义词定位，不用某个选项里的醒目原词直接作答。", "why": "干扰项常故意照抄原文。", "example": "题干问 purpose，应找目标表达，而不是看到 price 就选含 price 的项。"},
        {"id": "evidence", "title": "先读证据，再回看选项", "action": "读完相关句及前后句，用自己的话说出原文答案。", "why": "先理解证据可以减少被选项措辞影响。", "example": "because galleries are quieter → 原文答案方向是“环境更安静”。"},
        {"id": "verify", "title": "逐项判支持、相反、没回答", "action": "为每项标记：完整支持/相反/相关但没回答/无证据。", "why": "单选要找到唯一完整项；多选每项都要独立通过。", "example": "原文提到地点，但题干问原因：地点项是相关但没回答。"},
        {"id": "distractors", "title": "排除三类干扰项", "action": "重点排除同词诱饵、半对半错、对象或因果被偷换。", "why": "错误选项通常不是全错，而是只改一个关键部分。", "example": "原文费用高导致退出，选项写退出导致费用高：因果反了。"},
        {"id": "count", "title": "锁定答案数量", "action": "单选只留一项；多选为每个已选项分别指出证据，再数数量。", "why": "相关性不能替代独立证据，数量也不能靠感觉。", "example": "Choose TWO 最终必须正好两个字母。"},
        {"id": "check", "title": "最后证明正确与错误", "action": "说清正确项为什么完整成立，以及最近的干扰项具体错在哪里。", "why": "能同时解释一对选项，答案才真正稳定。", "example": "B 有完整原因证据；C 只是结果，没有回答 Why。"},
    ],
    "matching": [
        {"id": "instructions", "title": "确认匹配对象和复用规则", "action": "看清要填段落、标题、人物还是地点，并圈 may be used more than once。", "why": "不同匹配题的顺序和复用规则不同。", "example": "段落字母可重复时，A 用过仍可再选 A。"},
        {"id": "task", "title": "说清题目在找什么", "action": "给题目贴标签：主旨、原因、例子、观点、地点功能或句子关系。", "why": "标签决定你应该验证整段功能还是一个细节。", "example": "a reason 要有完整因果；an example 要有具体实例。"},
        {"id": "map", "title": "建立段落或对象地图", "action": "每段或每个对象只写一行短标签，记录主要功能和关键限制。", "why": "地图能避免每做一题都重新通读全文。", "example": "B：搬迁原因；C：服务实例；Mia：重时间灵活。"},
        {"id": "anchors", "title": "先做有独特路标的题", "action": "优先处理人名、数字、地点、专业词，再做没有路标的抽象题。", "why": "先拿确定分，还能顺便完善全文地图。", "example": "2018 只出现一次，可先定位候选段。"},
        {"id": "paraphrase", "title": "把题干换成简单意思", "action": "将抽象名词还原为动词，将同义表达写在路标旁。", "why": "匹配题很少逐字照抄。", "example": "concern about cost = worries it is expensive。"},
        {"id": "locate", "title": "缩小到一到两个候选", "action": "用地图、路标和同义词找候选，但先不立刻写答案。", "why": "多个段落可能都有同一主题词。", "example": "两段都谈交通，只有一段解释为什么容易到达。"},
        {"id": "verify", "title": "验证完整功能或完整特征", "action": "读完整信息块，确认对象、动作、原因和限制都属于同一处。", "why": "不能拼接两段或两个人的真实信息。", "example": "A 提供电脑，B 对所有人开放，不能拼成 A 对所有人开放。"},
        {"id": "contrast", "title": "两个候选都像时找差异", "action": "写出各自独特点，检查转折后重点和题目要求的范围。", "why": "共同主题不能决定答案，差异才决定。", "example": "一个地点仅会员，一个向所有访客开放。"},
        {"id": "eliminate", "title": "用排除表解决剩余题", "action": "先固定有直接证据的匹配，再核对剩余选项，但不强迫一一对应。", "why": "排除法只能在遵守复用规则时使用。", "example": "可重复时不能因为 A 已用过就排除 A。"},
        {"id": "check", "title": "提交前查地图", "action": "逐题确认题目功能、候选标签、直接证据和复用规则。", "why": "最后复核可发现按同词或想当然一一对应的答案。", "example": "标题是否罩住整段，而非只罩住一个例子？"},
    ],
    "completion": [
        {"id": "instructions", "title": "圈词数和来源规则", "action": "圈 NO MORE THAN、ONE WORD ONLY、AND/OR A NUMBER，并确认是否必须使用原文词或词库。", "why": "答案意思正确但超词，仍然判错。", "example": "NO MORE THAN TWO WORDS 是最多两词，不是必须两词。"},
        {"id": "structure", "title": "先读题目结构", "action": "句子看左右；摘要看标题和逻辑；笔记看层级；表格看行列；流程看箭头；图示看位置。", "why": "版式本身就在告诉你答案属于什么信息。", "example": "Price 列决定填价格，不是物品名称。"},
        {"id": "grammar", "title": "预测词性和形式", "action": "根据冠词、介词、情态动词、谓语和并列结构，写下名词/动词/形容词/数字及单复数。", "why": "先知道空格形状，能快速排除大量相关但不合语法的词。", "example": "must ____ → 动词原形；three ____ → 复数名词。"},
        {"id": "meaning", "title": "预测信息类型", "action": "再写答案含义：人、地点、时间、原因、材料、动作、部件或结果。", "why": "词性相同的候选很多，含义才能继续缩小范围。", "example": "Where + 介词后空格 → 地点名词短语。"},
        {"id": "anchors", "title": "选择定位词和同义词", "action": "圈专有名词、数字、罕见名词和逻辑关系，同时写一两个可能的同义表达。", "why": "题干和原文通常不使用完全相同的句子。", "example": "receive 可能对应 be given；cheap 可能对应 low-cost。"},
        {"id": "locate", "title": "按顺序找到证据区", "action": "从上一题证据之后继续找；摘要、流程和多数填空通常按原文顺序。", "why": "限定搜索区域比全文反复扫描更快更稳。", "example": "第 16 题答案一般在第 15 题证据之后。"},
        {"id": "candidate", "title": "抄出候选原文词", "action": "先完整圈出可能短语，再标中心词和必要修饰词，不立即删词。", "why": "先保留证据边界，之后才能有依据地缩短。", "example": "圈 a reusable bottle，再判断题干是否已给 a。"},
        {"id": "boundary", "title": "确定最短完整边界", "action": "删掉题干已有词和无关解释；保留中心词、必要方向词、单位和区分答案所需的修饰词。", "why": "过长会超词，过短可能失去真正答案。", "example": "图中有两个 valve 时要写 lower valve，不能只写 valve。"},
        {"id": "replace", "title": "放回题目朗读", "action": "检查词性、搭配、单复数、时态、行列或空间位置和整句意思。", "why": "找到原文词不等于它适合这个空格。", "example": "a reusable bottle 语法正确；a reusable bottles 不正确。"},
        {"id": "check", "title": "数词、拼写、写答案", "action": "最后数词，检查抄写、复数 -s、连字符和数字单位。", "why": "填空题最后常败在形式而非理解。", "example": "题面已写 kg 时只填 12；没有单位时按规则保留。"},
    ],
}


COMMON_WORD_GUESSING_STEPS: list[dict[str, str]] = [
    {"title": "先判断：这个词必须懂吗？", "action": "如果它是人名、地名或只在例子里出现，可先当作标签；如果它位于题干核心动作、否定、比较、范围或两个选项的差异处，就必须处理。", "example": "Green Hall 不必翻译；not available 中 not 必须看懂。"},
    {"title": "先看词性，不急着翻译", "action": "用冠词、介词、情态动词、词尾和句子位置判断它是人/物、动作、性质还是方式。", "example": "-tion 常见名词，-ive 常见形容词，-ly 常见副词；这只是线索，不是绝对规则。"},
    {"title": "看同一句里的定义或改写", "action": "留意 is called、means、that is、in other words、破折号、括号和同位语。", "example": "arboretum, a garden containing many kinds of trees → 后半句直接解释生词。"},
    {"title": "看逻辑词决定方向", "action": "but/however 后通常与前面相反；because/due to 后是原因；therefore/as a result 后是结果。", "example": "The room is compact but comfortable：即使不懂 compact，也知道它与 comfortable 构成转折。"},
    {"title": "用例子猜上位意思", "action": "such as、including、for example 后的熟词可以解释前面的陌生大类。", "example": "protective clothing such as gloves and helmets → protective clothing 是防护用品。"},
    {"title": "拆前缀、词根和后缀", "action": "只使用你确定的常见部分：un-/in- 表否定，re- 表再次，pre- 表之前，-less 表没有，-er 常表人或工具。", "example": "reusable = re（再次）+ use + able（能……的）→ 可重复使用的。"},
    {"title": "用上下句做替换测试", "action": "先给生词放入一个很宽的中文占位词，如“某种服务/某种变化/某种态度”，看句子逻辑是否成立。", "example": "The scheme was costly; consequently it was abandoned → abandoned 至少可猜为“被停止/放弃”。"},
    {"title": "仍猜不到时，不停留", "action": "保留生词标签，利用同义词、其他限定条件和排除法继续；只有当它决定两个候选的区别时才回头。", "example": "地点匹配中未知设施名可记作 facility X，再用开放对象和时间匹配。"},
]


FAMILY_VOCABULARY_GUIDES: dict[str, dict[str, Any]] = {
    "judgement": {
        "must_understand": ["题干主语和核心动作", "否定、数量、频率、情态和比较词", "观点主人与态度词"],
        "can_delay": ["人物职业的细节", "例子中的专有名词", "不改变主张的装饰性形容词"],
        "fallback": "把未知核心词标成 X，先比较其前后的否定、范围、时间和因果；如果 X 决定同义还是相反，最后回到上下文猜义，不能用常识补。",
    },
    "choice": {
        "must_understand": ["问题词和 NOT/EXCEPT", "各选项之间不同的词", "因果、目的、态度和程度词"],
        "can_delay": ["所有选项共同拥有的生词", "背景人名地名", "不影响选项差异的例子细节"],
        "fallback": "先比较选项共同部分和不同部分；共同生词可以暂时当 X，优先用能理解的对象、时间、范围和逻辑排除。",
    },
    "matching": {
        "must_understand": ["reason/example/problem/opinion 等信息功能词", "对象之间真正不同的态度或限制", "复用说明"],
        "can_delay": ["人名地名本身", "作为定位标记的专业词", "不影响段落功能的个别细节"],
        "fallback": "生词可先当作标签，不必翻译；给段落写“解释X原因”“反对X方法”等功能标签，仍可完成多数匹配。",
    },
    "completion": {
        "must_understand": ["空格左右决定词性的词", "题目答案类型和行列/箭头关系", "决定候选边界的中心词与修饰词"],
        "can_delay": ["远离空格的背景词", "不参与定位的例子", "答案区域之外的专业解释"],
        "fallback": "先用语法确定答案形状，再用题面逻辑确定信息类型；即使不懂整句，也可通过原文同义位置和放回检查缩小到正确原词。",
    },
}


LONG_SENTENCE_STEPS: list[dict[str, str]] = [
    {"title": "先找真正的谓语动词", "action": "忽略逗号里的说明，先找谁做了什么或谁是什么。", "example": "The centre, which opened in May, offers free classes. → 主干：centre offers classes。"},
    {"title": "再找主语和宾语", "action": "问“谁/什么 + 做什么 + 对谁/什么”，先得到最短主干。", "example": "Researchers found that prices affected attendance. → researchers found X；X 是后面的从句。"},
    {"title": "用连接词切成小块", "action": "在 and、but、because、although、which、that、when 前画斜线，一块一块读。", "example": "Although useful / the plan was rejected / because it was costly。"},
    {"title": "给从句贴功能标签", "action": "标原因、结果、转折、条件、时间或解释，不必逐词翻译。", "example": "because it was costly = 原因块；although useful = 让步背景。"},
    {"title": "追代词指向", "action": "把 it、they、this、such a method 换回真正名词，再读一次。", "example": "The scheme began in June. It served seniors. → It = scheme。"},
    {"title": "把否定、比较和范围放回主干", "action": "最后补回 not、only、more than、some、may 等会改变答案的小词。", "example": "may help some users 不能读成 helps all users。"},
    {"title": "只翻译与题目有关的关系", "action": "能说清对象、动作、时间、范围和逻辑就够了，不需要把整句翻译得漂亮。", "example": "做判断题时，只需知道“计划因费用高被拒绝”，其余修饰可暂缓。"},
]


FAMILY_CHECKLISTS: dict[str, list[str]] = {
    "judgement": [
        "题干和原文是同一对象、同一时间、同一观点主人吗？",
        "原文完整说到了题干关系，还是只提到相关主题？",
        "我是依据同义、明确相反还是信息不足作答的吗？",
        "all/some、may/must、often/always、before/after 是否一致？",
        "我的答案能指向具体证据，而不是常识吗？",
    ],
    "choice": [
        "我圈对了选择数量和 NOT/EXCEPT 吗？",
        "正确项完整回答了题干真正的问题吗？",
        "选项的对象、动作、原因、时间和范围都成立吗？",
        "每个多选答案都有独立证据吗？",
        "我能说清最近的干扰项具体错在哪里吗？",
    ],
    "matching": [
        "我确认了匹配对象、顺序规律和复用规则吗？",
        "我匹配的是段落功能/完整特征，而不是一个相同单词吗？",
        "对象、动作和限制来自同一个段落、人物或地点吗？",
        "主旨标题能覆盖大部分段落，而不是一个例子吗？",
        "两个候选都像时，我比较了真正差异吗？",
    ],
    "completion": [
        "我圈了词数、数字和原文词/词库规则吗？",
        "答案词性、单复数和信息类型符合空格吗？",
        "答案来自正确的行列、箭头、位置或原文顺序吗？",
        "我删掉题干已有词，并保留了必要中心词和修饰词吗？",
        "放回后语法、意思、拼写和词数全部正确吗？",
    ],
}


def course_ids() -> tuple[str, ...]:
    return tuple(_BLUEPRINT_BY_ID)


def _course_method(blueprint: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    return (
        copy.deepcopy(FAMILY_EXECUTION_STEPS[blueprint["family"]]),
        copy.deepcopy(FAMILY_CHECKLISTS[blueprint["family"]]),
    )


def _catalog_item(blueprint: dict[str, Any]) -> dict[str, Any]:
    steps, checklist = _course_method(blueprint)
    opening = COURSE_OPENINGS[blueprint["id"]]
    return {
        "id": blueprint["id"],
        "title": blueprint["title"],
        "family": blueprint["family"],
        "family_label": blueprint["family_label"],
        "category": blueprint["category"],
        "summary": blueprint["summary"],
        "first_move": opening["say"],
        "suggested_minutes": 25,
        "step_count": len(steps),
        "checklist_count": len(checklist),
        "section_count": 12,
        "offline_only": True,
    }


def build_method_course_catalog(tests: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    del tests  # Kept only for compatibility with older internal callers.
    courses = [_catalog_item(item) for item in COURSE_BLUEPRINTS]
    return {
        "mode": "offline_instruction_manual",
        "uses_ai": False,
        "course_count": len(courses),
        "families": [
            {"id": "judgement", "label": "判断题", "description": "先判说没说，再判同义或相反"},
            {"id": "choice", "label": "选择题", "description": "抓题干焦点，用证据逐项排除"},
            {"id": "matching", "label": "匹配题", "description": "先建地图，再匹配完整功能或特征"},
            {"id": "completion", "label": "填空与简答", "description": "预测答案形状，定位原词并放回检查"},
        ],
        "courses": courses,
    }


def build_method_course_detail(course_id: str, tests: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    del tests  # Method courses are deterministic and independent of the bank.
    blueprint = _BLUEPRINT_BY_ID.get(str(course_id))
    if not blueprint:
        raise KeyError(course_id)
    steps, checklist = _course_method(blueprint)
    family_teaching = copy.deepcopy(FAMILY_TEACHING[blueprint["family"]])
    course_teaching = copy.deepcopy(COURSE_TEACHING[course_id])
    family_foundation = copy.deepcopy(FAMILY_FOUNDATIONS[blueprint["family"]])
    family_foundation["rules"].extend(copy.deepcopy(COURSE_FOUNDATION_ADDITIONS.get(course_id, [])))
    difficulty_ladder = family_teaching["difficulty_ladder"]
    difficulty_ladder[0]["course_tip"] = course_teaching["easy_rule"]
    difficulty_ladder[2]["warning_signals"] = course_teaching["hard_signals"]
    detail = _catalog_item(blueprint)
    detail.update(
        {
            "mode": "offline_instruction_manual",
            "uses_ai": False,
            "offline_policy": "本页只展示预先编写并经过测试的固定做题方法；不调用 AI、不分析个人记录、不生成答案。",
            "recognition": list(blueprint["recognition"]),
            "opening": copy.deepcopy(COURSE_OPENINGS[course_id]),
            "child_guide": {
                "plain_language": course_teaching["plain_language"],
                "goal": family_teaching["goal"],
                "memory_sentence": course_teaching["memory_sentence"],
                "before_you_start": family_teaching["before_you_start"],
            },
            "difficulty_ladder": difficulty_ladder,
            "foundation_guide": {
                "title": f"{blueprint['title']}：{family_foundation['title']}",
                "intro": family_foundation["intro"],
                "answer_form": COURSE_ANSWER_FORMS[course_id],
                "rules": family_foundation["rules"],
            },
            "decision_guide": copy.deepcopy(COURSE_DECISION_GUIDES[course_id]),
            "vocabulary_guide": {
                **copy.deepcopy(FAMILY_VOCABULARY_GUIDES[blueprint["family"]]),
                "steps": copy.deepcopy(COMMON_WORD_GUESSING_STEPS),
                "critical_words": list(COURSE_OPENINGS[course_id]["critical_words"]),
            },
            "long_sentence_guide": copy.deepcopy(LONG_SENTENCE_STEPS),
            "mini_example": course_teaching["mini_example"],
            "standard_method": steps,
            "special_rules": course_teaching["special_rules"],
            "hard_rescue": family_teaching["hard_rescue"],
            "time_plan": family_teaching["time_plan"],
            "traps": list(blueprint["traps"]),
            "checklist": checklist,
        }
    )
    return detail
