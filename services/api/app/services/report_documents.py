from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _title(report: dict[str, Any], fallback: str) -> str:
    assignment = report.get("assignment") or {}
    return str(assignment.get("title") or fallback or "IELTS G类阅读教师报告")


def _set_docx_font(run: Any, *, size: int = 10, bold: bool = False) -> None:
    run.font.name = "Arial"
    run.font.size = Pt(size)
    run.bold = bold
    properties = run._element.get_or_add_rPr()
    fonts = properties.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    fonts.set(qn("w:eastAsia"), "Microsoft YaHei")


def _docx_paragraph(document: Document, text: str, *, bold: bool = False) -> None:
    paragraph = document.add_paragraph()
    _set_docx_font(paragraph.add_run(text), bold=bold)


def build_teacher_docx(report: dict[str, Any], *, title: str) -> bytes:
    document = Document()
    section = document.sections[0]
    section.top_margin = Mm(16)
    section.bottom_margin = Mm(16)
    section.left_margin = Mm(18)
    section.right_margin = Mm(18)

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_docx_font(heading.add_run(_title(report, title)), size=18, bold=True)
    subheading = document.add_paragraph()
    subheading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_docx_font(subheading.add_run("IELTS General Training Reading · 确定性学习报告"), size=9)

    assignment = report.get("assignment") or {}
    if assignment.get("description"):
        _docx_paragraph(document, f"作业说明：{assignment['description']}")
    if assignment.get("due_at"):
        _docx_paragraph(document, f"截止时间：{assignment['due_at']}")
    modules = assignment.get("modules") or []
    if modules:
        _docx_paragraph(
            document,
            "作业模块：" + "；".join(
                f"{module.get('title')}（{len(module.get('session_ids') or [])}条记录）"
                for module in modules
            ),
        )

    document.add_heading("一、学习概览", level=1)
    summary = report.get("summary") or {}
    table = document.add_table(rows=2, cols=4)
    table.style = "Table Grid"
    labels = ("练习次数", "累计正确率", "总题数", "总用时")
    values = (
        summary.get("session_count", 0),
        f"{summary.get('accuracy', 0)}%",
        summary.get("total_questions", 0),
        f"{summary.get('total_elapsed_seconds', 0)} 秒",
    )
    for index, value in enumerate(labels):
        _set_docx_font(table.rows[0].cells[index].paragraphs[0].add_run(str(value)), bold=True)
    for index, value in enumerate(values):
        _set_docx_font(table.rows[1].cells[index].paragraphs[0].add_run(str(value)))

    document.add_heading("二、确定性解读", level=1)
    for insight in report.get("deterministic_interpretation") or ["当前样本不足，暂不作能力定性。"]:
        _docx_paragraph(document, f"• {insight}")

    document.add_heading("三、题型表现", level=1)
    type_rows = report.get("question_type_matrix") or []
    type_table = document.add_table(rows=1, cols=5)
    type_table.style = "Table Grid"
    for index, label in enumerate(("题型", "正确", "总数", "正确率", "状态")):
        _set_docx_font(type_table.rows[0].cells[index].paragraphs[0].add_run(label), bold=True)
    for row in type_rows:
        cells = type_table.add_row().cells
        values = (
            row.get("question_type") or row.get("question_subtype") or "未分类",
            row.get("correct", 0),
            row.get("total", 0),
            f"{row.get('accuracy', 0)}%",
            row.get("status_label", ""),
        )
        for index, value in enumerate(values):
            _set_docx_font(cells[index].paragraphs[0].add_run(str(value)))

    document.add_heading("四、代表性错题", level=1)
    representative = report.get("representative_questions") or []
    if not representative:
        _docx_paragraph(document, "暂无代表性错题。")
    for item in representative:
        _docx_paragraph(
            document,
            f"Q{item.get('question_number')} · {item.get('question_type')} · {item.get('prompt')}",
            bold=True,
        )
        _docx_paragraph(
            document,
            f"学生答案：{item.get('user_answer')}    标准答案：{item.get('correct_answer')}",
        )
        if item.get("analysis"):
            _docx_paragraph(document, f"解析：{item['analysis']}")

    document.add_heading("五、数据说明", level=1)
    for note in report.get("data_notes") or []:
        _docx_paragraph(document, f"• {note}")
    _docx_paragraph(document, "本报告不调用 AI；标准答案、判分和 Band 规则没有改变。", bold=True)

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pdf_styles() -> dict[str, ParagraphStyle]:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except KeyError:
        pass
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ChineseTitle",
            parent=base["Title"],
            fontName="STSong-Light",
            fontSize=18,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "ChineseSubtitle",
            parent=base["Normal"],
            fontName="STSong-Light",
            fontSize=8,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#62757B"),
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "ChineseHeading",
            parent=base["Heading2"],
            fontName="STSong-Light",
            fontSize=13,
            leading=18,
            spaceBefore=10,
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "ChineseBody",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=9,
            leading=14,
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "ChineseSmall",
            parent=base["BodyText"],
            fontName="STSong-Light",
            fontSize=7.5,
            leading=11,
        ),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def build_teacher_pdf(report: dict[str, Any], *, title: str) -> bytes:
    buffer = BytesIO()
    styles = _pdf_styles()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=_title(report, title),
        author="IELTS G类阅读 AI 教练",
    )
    story: list[Any] = [
        _p(_title(report, title), styles["title"]),
        _p("IELTS General Training Reading · 确定性学习报告", styles["subtitle"]),
    ]
    summary = report.get("summary") or {}
    summary_data = [
        [_p(label, styles["small"]) for label in ("练习次数", "累计正确率", "总题数", "总用时")],
        [
            _p(summary.get("session_count", 0), styles["body"]),
            _p(f"{summary.get('accuracy', 0)}%", styles["body"]),
            _p(summary.get("total_questions", 0), styles["body"]),
            _p(f"{summary.get('total_elapsed_seconds', 0)} 秒", styles["body"]),
        ],
    ]
    summary_table = Table(summary_data, colWidths=[42 * mm] * 4)
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF6F3")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#BFCFD3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([summary_table, Spacer(1, 6), _p("确定性解读", styles["heading"])])
    for insight in report.get("deterministic_interpretation") or ["当前样本不足，暂不作能力定性。"]:
        story.append(_p(f"• {insight}", styles["body"]))

    story.append(_p("题型表现", styles["heading"]))
    type_data = [[_p(value, styles["small"]) for value in ("题型", "正确", "总数", "正确率", "状态")]]
    for row in report.get("question_type_matrix") or []:
        type_data.append([
            _p(row.get("question_type") or row.get("question_subtype") or "未分类", styles["small"]),
            _p(row.get("correct", 0), styles["small"]),
            _p(row.get("total", 0), styles["small"]),
            _p(f"{row.get('accuracy', 0)}%", styles["small"]),
            _p(row.get("status_label", ""), styles["small"]),
        ])
    type_table = Table(type_data, colWidths=[75 * mm, 18 * mm, 18 * mm, 25 * mm, 32 * mm], repeatRows=1)
    type_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF6F3")),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#C7D5D8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([type_table, PageBreak(), _p("代表性错题", styles["heading"])])
    representative = report.get("representative_questions") or []
    if not representative:
        story.append(_p("暂无代表性错题。", styles["body"]))
    for item in representative:
        story.append(_p(
            f"Q{item.get('question_number')} · {item.get('question_type')} · {item.get('prompt')}",
            styles["body"],
        ))
        story.append(_p(
            f"学生答案：{item.get('user_answer')}　标准答案：{item.get('correct_answer')}",
            styles["small"],
        ))
        if item.get("analysis"):
            story.append(_p(f"解析：{item['analysis']}", styles["small"]))
        story.append(Spacer(1, 5))
    story.append(_p("数据说明", styles["heading"]))
    for note in report.get("data_notes") or []:
        story.append(_p(f"• {note}", styles["small"]))
    story.append(_p("本报告不调用 AI；标准答案、判分和 Band 规则没有改变。", styles["body"]))
    document.build(story)
    return buffer.getvalue()
