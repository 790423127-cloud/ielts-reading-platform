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


def build_foundation_catalog() -> list[dict[str, Any]]:
    return [dict(course) for course in FOUNDATION_COURSES]


def get_foundation_course(course_id: str) -> dict[str, Any] | None:
    return next(
        (course for course in build_foundation_catalog() if course["id"] == course_id),
        None,
    )
