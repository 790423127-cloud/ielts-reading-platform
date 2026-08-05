from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


SOURCE_NAME = re.compile(
    r"^C(?P<book>\d+)-Test (?P<test>[A-B]|\d+)-(?:Section|Passage) (?P<part>\d+)$",
    re.IGNORECASE,
)
QUESTION_RANGE = re.compile(
    r"\bQuestions?\s*(?P<start>\d+)(?:\s*[-\u2013]\s*(?P<end>\d+))?",
    re.IGNORECASE,
)
CHOICE_COUNT = re.compile(
    r"\b(?:choose|which)\s+(?P<count>two|three|four|2|3|4)\b",
    re.IGNORECASE,
)
ALLOWED_TAGS = {
    "b", "br", "div", "em", "h1", "h2", "h3", "hr", "i", "img", "li",
    "ol", "p", "span", "strong", "table", "tbody", "td", "tfoot", "th",
    "thead", "tr", "u", "ul",
}
VOID_TAGS = {"br", "hr", "img"}
ALLOWED_ATTRIBUTES = {
    "align", "alt", "border", "colspan", "height", "rowspan", "src", "style",
    "title", "valign", "width",
}
ALLOWED_STYLES = {
    "background-color", "border", "border-collapse", "border-color", "border-style",
    "border-width", "color", "font-style", "font-weight", "height", "list-style-type",
    "margin", "margin-bottom", "margin-left", "margin-right", "margin-top", "padding",
    "padding-bottom", "padding-left", "padding-right", "padding-top", "text-align",
    "text-decoration", "vertical-align", "width",
}


def sanitize_style(value: str) -> str:
    declarations: list[str] = []
    for declaration in value.split(";"):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        name = name.strip().lower()
        raw_value = raw_value.strip()
        lowered = raw_value.lower()
        if name not in ALLOWED_STYLES:
            continue
        if any(token in lowered for token in ("expression", "javascript:", "url(")):
            continue
        declarations.append(f"{name}: {raw_value}")
    return "; ".join(declarations)


class SafeHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if name not in ALLOWED_ATTRIBUTES or value is None:
                continue
            if name == "style":
                value = sanitize_style(value)
                if not value:
                    continue
            if name == "src" and not re.match(r"^(?:https?:|data:image/)", value, re.IGNORECASE):
                continue
            safe_attrs.append(f'{name}="{html.escape(value, quote=True)}"')
        suffix = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.output.append(f"<{tag}{suffix}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.output.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")


def sanitize_html(value: Any) -> str:
    parser = SafeHtml()
    parser.feed(str(value or ""))
    parser.close()
    return "".join(parser.output).strip()


def displayed_question_range(value: Any) -> tuple[int, int] | None:
    plain_text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    match = QUESTION_RANGE.search(plain_text)
    if not match:
        return None
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    return start, end


def plain_text(value: Any) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).strip()


def interaction_mode(question_type: int) -> str:
    return {
        0: "text_entry",
        1: "single_choice",
        2: "multiple_choice",
        3: "judgement",
        4: "matching_matrix",
    }.get(question_type, "text_entry")


def required_choices(descriptions: Any) -> int | None:
    match = CHOICE_COUNT.search(plain_text(descriptions))
    if not match:
        return None
    token = match.group("count").lower()
    return {"two": 2, "three": 3, "four": 4}.get(
        token, int(token) if token.isdigit() else None
    )


def preview_answer_control() -> str:
    return '<input class="text-answer" type="text" aria-label="answer">'


def replace_answer_blanks(value: str) -> str:
    return re.sub(r"(?:\.{4,}|_{4,})", preview_answer_control(), value)


def matching_matrix_rows(value: str, start: int, end: int) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for fragment in re.split(r"(?:</p>|<br\s*/?>)", value, flags=re.IGNORECASE):
        text = re.sub(r"(?:\.{4,}|_{4,})", "", plain_text(fragment)).strip()
        match = re.match(r"^(\d+)\s+(.*)$", text)
        if match:
            rows.append((int(match.group(1)), match.group(2).strip()))
    if rows:
        return rows
    return [(number, "") for number in range(start, end + 1)]


def render_matching_matrix(
    questions_html: str,
    match_options: list[dict[str, str]],
    start: int,
    end: int,
) -> str:
    headers = "".join(
        f'<th scope="col">{html.escape(str(option.get("index") or ""))}</th>'
        for option in match_options
    )
    rows = []
    for number, prompt in matching_matrix_rows(questions_html, start, end):
        cells = "".join(
            '<td><label class="matrix-radio"><input type="radio" '
            f'name="matrix-{number}"><span></span></label></td>'
            for _ in match_options
        )
        rows.append(
            f'<tr><th scope="row"><strong>{number}</strong> {html.escape(prompt)}</th>{cells}</tr>'
        )
    return (
        '<div class="matching-matrix-wrap"><table class="matching-matrix">'
        f'<thead><tr><th></th>{headers}</tr></thead><tbody>{"".join(rows)}</tbody>'
        '</table></div>'
    )


def render_question_group(group: dict[str, Any]) -> str:
    question_type = int(group.get("question_type") or 0)
    start = int(group.get("start_index") or group.get("display_start") or 0)
    end = int(group.get("end_index") or group.get("display_end") or start)
    match_options = group.get("match_options") or []
    sections = [
        '<section class="question-group">',
        f'<div class="instructions">{group.get("instructions_html") or ""}</div>',
    ]
    questions_html = str(group.get("questions_html") or "")
    structured_questions = group.get("structured_questions") or []
    if question_type == 4 and questions_html and match_options:
        meaningful_options = [
            option
            for option in match_options
            if plain_text(option.get("content_html"))
            not in {
                str(option.get("index") or ""),
                f'Section {option.get("index") or ""}',
            }
        ]
        if meaningful_options:
            title = html.escape(str(group.get("options_title") or "Options"))
            options = "".join(
                '<li><strong>' + html.escape(str(option.get("index") or "")) + '</strong> '
                + (option.get("content_html") or "") + '</li>'
                for option in match_options
            )
            sections.append(f'<aside class="option-bank"><b>{title}</b><ul>{options}</ul></aside>')
        sections.append(render_matching_matrix(questions_html, match_options, start, end))
    elif question_type == 0 and questions_html:
        rendered = replace_answer_blanks(questions_html)
        sections.append(f'<div class="source-questions-content">{rendered}</div>')
    elif structured_questions:
        for index, question in enumerate(structured_questions):
            display_number = start + index if start else index + 1
            if question_type == 2 and end > start:
                number_label = f"{start}-{end}"
            else:
                number_label = str(display_number)
            sections.append('<article class="question-row">')
            sections.append(
                f'<div class="question-prompt"><strong>{number_label}</strong> '
                f'{question.get("content_html") or ""}</div>'
            )
            input_type = "checkbox" if question_type == 2 else "radio"
            name = f'g{group.get("position", 0)}q{index}'
            for option_index, option in enumerate(question.get("options") or []):
                letter = chr(65 + option_index) if question_type in {1, 2} else ""
                sections.append(
                    '<label class="source-option">'
                    f'<input type="{input_type}" name="{name}">'
                    f'<b>{letter}</b><span>{option.get("content_html") or ""}</span></label>'
                )
            sections.append('</article>')
    else:
        control_count = max(1, end - start + 1)
        for index in range(control_count):
            number = start + index if start else index + 1
            sections.append(
                f'<div class="fallback-answer"><strong>{number}</strong> '
                f'{preview_answer_control()}</div>'
            )
    sections.append('</section>')
    return "".join(sections)


def render_full_preview(part: dict[str, Any]) -> str:
    questions = "".join(render_question_group(group) for group in part["question_groups"])
    test_id = html.escape(part["test_id"])
    part_number = int(part["part_number"])
    source_name = html.escape(part["source_name"])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{source_name}</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;color:#1b1b1b}}
body{{overflow:hidden;background:#fff}}.source-header{{height:93px;display:flex;align-items:center;gap:24px;padding:0 28px;border-bottom:1px solid #ddd}}
.brand{{color:#3277d5;font-size:22px;font-weight:800}}.source-title strong{{display:block;font-size:16px}}.source-title span{{color:#777;font-size:13px}}
.partbar{{height:70px;padding:14px 30px;border-bottom:1px solid #ddd;background:#fbfaf7;line-height:1.55}}
.workspace{{height:calc(100vh - 203px);display:grid;grid-template-columns:44% 12px 56%}}.pane{{min-width:0;overflow:auto;padding:16px 20px 70px;font-size:16px;line-height:1.48}}
.divider{{background:#999}}.source-article{{overflow-wrap:anywhere}}.source-article img{{max-width:100%;height:auto}}table{{max-width:100%;border-collapse:collapse}}td,th{{padding:7px 9px;vertical-align:top}}
.instructions{{margin-bottom:20px}}.instructions p{{margin:0 0 10px}}.instructions div{{margin:0 0 8px}}.question-group{{margin-bottom:32px}}
.question-row{{padding:13px 8px 16px;border-bottom:1px solid #ececec}}.question-prompt{{margin-bottom:10px;line-height:1.6}}.question-prompt>strong{{margin-right:8px}}
.source-option{{display:flex;align-items:flex-start;gap:8px;margin:8px 0;padding-left:2px}}.source-option input{{margin-top:4px}}.source-option b{{min-width:18px}}
.source-questions-content>p,.source-questions-content>div{{margin:13px 0;line-height:1.7}}.text-answer,.source-questions-content input{{width:142px;height:31px;margin:0 6px;border:1px solid #8e8e8e;background:#fff}}
.option-bank{{margin:12px 0 18px;padding:13px 16px;border:1px solid #d7d7d7;background:#f6f6f6}}.option-bank ul{{margin:9px 0 0;padding:0;list-style:none}}.option-bank li{{margin:6px 0}}.option-bank li strong{{display:inline-block;min-width:24px}}
.matching-matrix-wrap{{margin-top:18px;overflow-x:auto}}.matching-matrix{{width:min(100%,920px);min-width:590px;border-collapse:collapse}}.matching-matrix th,.matching-matrix td{{height:70px;border:1px solid #b9b9b9}}.matching-matrix thead th{{height:70px;border-bottom:3px solid #111;text-align:center}}.matching-matrix thead th:first-child,.matching-matrix tbody th{{width:58.6%;border-right:3px solid #111;text-align:left}}.matching-matrix tbody th{{padding:0 16px;font-weight:400}}.matching-matrix tbody td{{width:8.28%;text-align:center}}.matrix-radio{{display:inline-grid;width:38px;height:38px;place-items:center}}.matrix-radio input{{position:absolute;opacity:0}}.matrix-radio span{{width:22px;height:22px;border:1px solid #c2c2c2;border-radius:50%;background:#eee}}
.fallback-answer{{margin:12px 0}}.dock{{position:fixed;right:0;bottom:0;left:0;height:40px;padding:10px 16px;border-top:1px solid #ddd;background:#fff;font-size:13px}}
.notice{{position:fixed;right:18px;top:12px;color:#8a5a00;font-size:12px}}@media(max-width:900px){{.workspace{{grid-template-columns:1fr}}.divider{{display:none}}.pane{{height:50%}}}}
</style>
</head>
<body>
<header class="source-header"><div class="brand">雅思哥 IELTS BRO</div><div class="source-title"><strong>{source_name}</strong><span>缓存原始数据完整预览</span></div></header>
<div class="notice">非软件实拍 · 不含答案</div>
<div class="partbar"><strong>Part {part_number}</strong><br>Read the text below and answer the questions.</div>
<main class="workspace"><section class="pane source-article">{part["passage_html"]}</section><div class="divider"></div><section class="pane source-questions">{questions}</section></main>
<footer class="dock">{test_id} · Part {part_number}</footer>
</body></html>"""


def local_reference(source_name: str) -> tuple[str, int] | None:
    match = SOURCE_NAME.match(source_name.strip())
    if not match:
        return None
    book = int(match.group("book"))
    raw_test = match.group("test").lower()
    if raw_test.isdigit():
        test_number = int(raw_test)
        if book == 12 and 5 <= test_number <= 8:
            test_number -= 4
        test_id = f"b{book}-test-{test_number}"
    else:
        test_id = f"b{book}-test-{raw_test}"
    return test_id, int(match.group("part"))


def extract_part(item: dict[str, Any], cache_file: Path) -> dict[str, Any] | None:
    source_name = str(item.get("passagesQuestion") or "").strip()
    reference = local_reference(source_name)
    if reference is None:
        return None
    test_id, part_number = reference
    question_groups = []
    for index, group in enumerate(item.get("questions") or []):
        question_json = group.get("questionJson") or {}
        descriptions = sanitize_html(question_json.get("descriptions"))
        question_type = int(group.get("questionType") or question_json.get("questionType") or 0)
        raw_answer_rows = group.get("answerJson") or []
        if isinstance(raw_answer_rows, str):
            try:
                raw_answer_rows = json.loads(raw_answer_rows)
            except json.JSONDecodeError:
                raw_answer_rows = []
        answer_count = len(raw_answer_rows) if isinstance(raw_answer_rows, list) else 0
        description_range = displayed_question_range(question_json.get("descriptions"))
        navigation_range = displayed_question_range(group.get("questionNavigation"))
        index_range = (
            int(question_json.get("startIndex") or 0),
            int(question_json.get("endIndex") or question_json.get("startIndex") or 0),
        )
        if question_type == 2 and description_range is not None:
            display_range = description_range
        else:
            candidates = [
                candidate
                for candidate in (navigation_range, description_range, index_range)
                if candidate and candidate[0] > 0 and candidate[1] >= candidate[0]
            ]
            display_range = next(
                (
                    candidate
                    for candidate in candidates
                    if answer_count > 0 and candidate[1] - candidate[0] + 1 == answer_count
                ),
                candidates[0] if candidates else None,
            )
        match_options = [
            {
                "index": str(option.get("index") or ""),
                "content_html": sanitize_html(option.get("content")),
            }
            for option in question_json.get("matchOptions") or []
            if isinstance(option, dict)
        ]
        structured_questions = [
            {
                "content_html": sanitize_html(question.get("content")),
                "options": [
                    {"content_html": sanitize_html(option.get("content"))}
                    for option in question.get("options") or []
                    if isinstance(option, dict)
                ],
            }
            for question in question_json.get("questions") or []
            if isinstance(question, dict)
        ]
        question_groups.append({
            "position": index,
            "navigation": str(group.get("questionNavigation") or ""),
            "display_start": display_range[0] if display_range else None,
            "display_end": display_range[1] if display_range else None,
            "start_index": int(question_json.get("startIndex") or 0),
            "end_index": int(question_json.get("endIndex") or 0),
            "question_type": question_type,
            "interaction_mode": interaction_mode(question_type),
            "required_choices": required_choices(question_json.get("descriptions")),
            "instructions_html": descriptions,
            "questions_html": sanitize_html(question_json.get("questionsContent")),
            "structured_questions": structured_questions,
            "match_options": match_options,
            "options_title": plain_text(question_json.get("optionsTitle")),
        })
    return {
        "test_id": test_id,
        "part_number": part_number,
        "source_name": source_name,
        "passage_html": sanitize_html(item.get("passagesContent")),
        "question_groups": question_groups,
        "cache_file": cache_file.name,
    }


def load_cache(cache_root: Path) -> list[dict[str, Any]]:
    extracted: dict[tuple[str, int], dict[str, Any]] = {}
    for cache_file in sorted(cache_root.iterdir(), key=lambda path: path.stat().st_mtime_ns):
        if not cache_file.is_file():
            continue
        try:
            payload = json.loads(cache_file.read_text("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            continue
        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            part = extract_part(item, cache_file)
            if part:
                extracted[(part["test_id"], part["part_number"])] = part
    return sorted(extracted.values(), key=lambda item: (item["test_id"], item["part_number"]))


def write_baseline_files(parts: list[dict[str, Any]], baseline_dir: Path) -> None:
    html_root = baseline_dir / "source-html"
    full_html_root = baseline_dir / "source-full-html"
    index_links: list[str] = []
    for part in parts:
        target = html_root / part["test_id"] / f"part-{part['part_number']}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(part["passage_html"], "utf-8")
        full_target = full_html_root / part["test_id"] / f"part-{part['part_number']}.html"
        full_target.parent.mkdir(parents=True, exist_ok=True)
        full_target.write_text(render_full_preview(part), "utf-8")
        relative = full_target.relative_to(full_html_root).as_posix()
        index_links.append(
            f'<li><a href="{html.escape(relative, quote=True)}">'
            f'{html.escape(part["source_name"])}</a></li>'
        )
    full_html_root.mkdir(parents=True, exist_ok=True)
    (full_html_root / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>IELTSBro full HTML baseline</title>'
        '<style>body{max-width:900px;margin:32px auto;font:16px/1.6 system-ui}li{margin:5px 0}</style>'
        '<h1>雅思哥 G 类阅读完整 HTML 基准</h1>'
        '<p>156 个 Part；包含文章区与答题区。由桌面端缓存原始数据生成，非软件实拍，不含答案。</p><ul>'
        + "".join(index_links) + '</ul>',
        "utf-8",
    )
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "parts": len(parts),
        "tests": len({part["test_id"] for part in parts}),
        "books": sorted({int(part["test_id"].split("-", 1)[0][1:]) for part in parts}),
        "question_groups": sum(len(part["question_groups"]) for part in parts),
        "full_preview_parts": len(parts),
    }
    (baseline_dir / "source-html-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        "utf-8",
    )


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    default_cache = Path(os.environ.get("APPDATA", "")) / "雅思哥机考软件" / "Cache" / "Cache_Data"
    default_output = (
        repository_root
        / "services"
        / "api"
        / "data"
        / "question-bank"
        / "passage_source_html.local.json"
    )
    parser = argparse.ArgumentParser(description="Extract sanitized IELTSBro passage layout HTML.")
    parser.add_argument("--cache-root", type=Path, default=default_cache)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--baseline-dir", type=Path)
    args = parser.parse_args()

    if not args.cache_root.is_dir():
        raise SystemExit(f"IELTSBro cache directory not found: {args.cache_root}")
    parts = load_cache(args.cache_root)
    payload = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "ieltsbro-desktop-http-cache",
        "parts": parts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    if args.baseline_dir:
        args.baseline_dir.mkdir(parents=True, exist_ok=True)
        write_baseline_files(parts, args.baseline_dir)
    print(json.dumps({
        "output": str(args.output),
        "parts": len(parts),
        "tests": len({part["test_id"] for part in parts}),
        "question_groups": sum(len(part["question_groups"]) for part in parts),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
