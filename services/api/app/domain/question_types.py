from __future__ import annotations

import re
from typing import Any

CATEGORY_GAP = "gap_fill"
CATEGORY_SINGLE = "single_choice"
CATEGORY_MULTI = "multiple_choice"
CATEGORY_MATCHING = "matching"
CATEGORY_JUDGEMENT = "judgement"

CATEGORY_LABELS = {
    CATEGORY_GAP: "填空与简答",
    CATEGORY_SINGLE: "单选题",
    CATEGORY_MULTI: "多选题",
    CATEGORY_MATCHING: "匹配题",
    CATEGORY_JUDGEMENT: "判断题",
}

TFNG = "true_false_not_given"
YNNG = "yes_no_not_given"
MC_SINGLE = "multiple_choice_single"
MC_MULTI = "multiple_choice_multiple"
MATCH_INFO = "matching_information"
MATCH_HEAD = "matching_headings"
MATCH_FEAT = "matching_features"
MATCH_END = "matching_sentence_endings"
MATCH_NAMES = "matching_names"
MATCH_PLACES = "matching_places"
SENT_COMP = "sentence_completion"
SUM_COMP = "summary_completion"
NOTE_COMP = "note_completion"
TABLE_COMP = "table_completion"
FLOW_COMP = "flow_chart_completion"
DIAGRAM_COMP = "diagram_label_completion"
SHORT_ANS = "short_answer"
OTHER = "other"

SUBTYPE_LABELS = {
    TFNG: "TRUE/FALSE/NOT GIVEN",
    YNNG: "YES/NO/NOT GIVEN",
    MC_SINGLE: "单选题",
    MC_MULTI: "多选题",
    MATCH_INFO: "信息匹配",
    MATCH_HEAD: "段落标题匹配",
    MATCH_FEAT: "特征匹配",
    MATCH_END: "句子结尾匹配",
    MATCH_NAMES: "人名匹配",
    MATCH_PLACES: "地点匹配",
    SENT_COMP: "句子填空",
    SUM_COMP: "摘要填空",
    NOTE_COMP: "笔记填空",
    TABLE_COMP: "表格填空",
    FLOW_COMP: "流程图填空",
    DIAGRAM_COMP: "图示填空",
    SHORT_ANS: "简答题",
    OTHER: "其他",
}

CATEGORY_SUBTYPES = {
    CATEGORY_JUDGEMENT: {TFNG, YNNG},
    CATEGORY_SINGLE: {MC_SINGLE},
    CATEGORY_MULTI: {MC_MULTI},
    CATEGORY_MATCHING: {
        MATCH_INFO, MATCH_HEAD, MATCH_FEAT, MATCH_END, MATCH_NAMES, MATCH_PLACES,
    },
    CATEGORY_GAP: {
        SENT_COMP, SUM_COMP, NOTE_COMP, TABLE_COMP, FLOW_COMP, DIAGRAM_COMP, SHORT_ANS,
    },
}

EXACT_SUBTYPES = tuple(
    subtype
    for category in (
        CATEGORY_JUDGEMENT,
        CATEGORY_SINGLE,
        CATEGORY_MULTI,
        CATEGORY_MATCHING,
        CATEGORY_GAP,
    )
    for subtype in sorted(CATEGORY_SUBTYPES[category])
)


def parse_option_item(option: Any) -> dict[str, str] | None:
    if option is None:
        return None
    if isinstance(option, str):
        text = option.strip()
        match = re.match(
            r"^([A-Z]|TRUE|FALSE|NOT GIVEN|YES|NO|T|F|NG|Y|N)[\.:\)]\s*(.*)$",
            text,
            re.I,
        )
        if match:
            return {"code": match.group(1).upper(), "text": match.group(2).strip()}
        if re.fullmatch(r"[A-Z]", text):
            return {"code": text.upper(), "text": ""}
        return {"code": text, "text": text}
    if isinstance(option, dict):
        code = str(
            option.get("code")
            or option.get("value")
            or option.get("title")
            or ""
        ).strip()
        text = str(
            option.get("text")
            or option.get("label")
            or option.get("content")
            or ""
        ).strip()
        if text and text.casefold() == code.casefold():
            text = ""
        if not code:
            match = re.match(r"^([A-Z])[\.:\)]\s*(.*)$", text)
            if match:
                code, text = match.group(1), match.group(2).strip()
        if not code:
            return None
        upper = code.upper()
        if upper in {"TRUE", "FALSE", "NOT GIVEN", "YES", "NO"} or re.fullmatch(r"[A-Z]", upper):
            code = upper
        return {"code": code, "text": text}
    return None


def normalize_options_raw(raw: Any) -> list[dict[str, str]]:
    if not raw:
        return []
    if isinstance(raw, dict) and not any(
        key in raw for key in ("value", "code", "label", "text")
    ):
        values = [parse_option_item({"code": key, "text": value}) for key, value in raw.items()]
    elif isinstance(raw, list):
        values = [parse_option_item(option) for option in raw]
    else:
        return []
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = value["code"].casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    roman = re.compile(r"^(?:i|ii|iii|iv|v|vi|vii|viii|ix|x)$", re.I)
    roman_codes = [item["code"] for item in output if roman.fullmatch(item["code"])]
    if len(roman_codes) >= 2 and any(len(code) > 1 for code in roman_codes):
        output = [
            {**item, "code": item["code"].lower() if roman.fullmatch(item["code"]) else item["code"]}
            for item in output
        ]
    return output


def normalize_options(group: dict[str, Any]) -> list[dict[str, str]]:
    options = normalize_options_raw(group.get("options") or group.get("shared_options"))
    if options:
        return options
    for question in group.get("questions") or []:
        options = normalize_options_raw(question.get("options"))
        if options:
            return options
    return []


def normalize_shared_options(group: dict[str, Any]) -> list[dict[str, str]]:
    """Return only options that are genuinely shared by every question in a group."""

    explicit = normalize_options_raw(group.get("options") or group.get("shared_options"))
    if explicit:
        return explicit
    questions = group.get("questions") or []
    question_options = []
    for question in questions:
        options = normalize_options_raw(question.get("options"))
        if not options:
            return []
        question_options.append(options)
    if not question_options or len(question_options) != len(questions):
        return []
    first = question_options[0]
    return first if all(options == first for options in question_options[1:]) else []


def _is_gap(instructions: str) -> bool:
    return any(
        cue in instructions
        for cue in (
            "no more than", "one word only", "words from the", "complete the sentences",
            "complete the notes", "complete the summary", "complete the table", "complete the flow",
        )
    )


def _options_are_letter_codes(options: list[dict[str, str]]) -> bool:
    codes = [str(option.get("code") or "").strip().upper() for option in options]
    return bool(codes) and all(re.fullmatch(r"[A-Z]", code) for code in codes if code)


def classify_subtype(instructions: str, group: dict[str, Any] | None = None) -> str:
    text = (instructions or "").casefold()
    group = group or {}
    options = normalize_options(group)

    if "true" in text and "false" in text and "not given" in text:
        return TFNG
    if "yes" in text and "no" in text and "not given" in text:
        return YNNG

    multi_letter = bool(
        re.search(r"choose\s+(two|three|four|2|3|4)\s+(letters|answers|options)", text)
        or re.search(r"which\s+(two|three|four)\s+(letters|answers)", text)
        or re.search(r"choose\s+(two|three|four)\s+from", text)
    )
    if multi_letter and options:
        return MC_MULTI

    if "heading" in text:
        return MATCH_HEAD
    if "ending" in text:
        return MATCH_END
    if any(cue in text for cue in ("people", "person", "names")) and (
        "match" in text or ("which" in text and len(options) >= 3)
    ):
        return MATCH_NAMES
    if any(cue in text for cue in ("place", "location", "city")) and (
        "match" in text or ("which" in text and len(options) >= 4 and not _is_gap(text))
    ):
        return MATCH_PLACES

    matching_cues = (
        "match", "which section", "which paragraph", "which sections", "which paragraphs",
        "contains the following", "mentions the following", "for which", "list of", "look at the following",
        "classify the following",
    )
    if any(cue in text for cue in matching_cues) and not _is_gap(text):
        if "feature" in text or "characteristic" in text:
            return MATCH_FEAT
        if options and _options_are_letter_codes(options):
            return MATCH_INFO if ("section" in text or "paragraph" in text) else MATCH_FEAT
        return MATCH_INFO

    if any(cue in text for cue in ("flow-chart", "flow chart", "flowchart")):
        return FLOW_COMP
    if any(cue in text for cue in ("label the diagram", "label the map", "label the plan")):
        return DIAGRAM_COMP
    if "table" in text:
        return TABLE_COMP
    if "summary" in text:
        return SUM_COMP
    if "notes" in text or ("note" in text and "complete" in text):
        return NOTE_COMP
    if "answer the questions" in text or "short answer" in text:
        return SHORT_ANS
    if any(cue in text for cue in ("complete", "no more than", "one word only", "words from")):
        return SENT_COMP
    if "choose" in text and options:
        return MC_SINGLE if 2 <= len(options) <= 5 else MATCH_FEAT
    if options and len(options) >= 5 and _options_are_letter_codes(options):
        return MATCH_INFO
    return OTHER


def subtype_to_category(subtype: str) -> str:
    for category, subtypes in CATEGORY_SUBTYPES.items():
        if subtype in subtypes:
            return category
    return CATEGORY_GAP


def enrich_test(test: dict[str, Any]) -> dict[str, Any]:
    for part in test.get("parts") or []:
        for group in part.get("groups") or []:
            subtype = classify_subtype(str(group.get("instructions") or ""), group)
            group["question_subtype"] = subtype
            group["question_type"] = subtype
            group["question_category"] = subtype_to_category(subtype)
            group["question_label"] = SUBTYPE_LABELS[subtype]
            options = normalize_shared_options(group)
            if options:
                group["normalized_options"] = options
            else:
                group.pop("normalized_options", None)
    return test
