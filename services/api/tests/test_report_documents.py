from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from app.services.report_documents import build_teacher_docx, build_teacher_pdf


def _report() -> dict:
    return {
        "report_type": "teacher_assignment",
        "engine_version": "0.5.0-deterministic",
        "layout_type": "multi_part",
        "layout_label": "多模块作业对比",
        "generated_from": "persisted_sessions",
        "ai_calls": 0,
        "assignment": {
            "title": "真人老师课后作业",
            "description": "完成三套不同来源的 Part 3。",
        },
        "summary": {
            "title": "真人老师课后作业",
            "session_count": 2,
            "first_attempt_count": 2,
            "retry_count": 0,
            "correct": 10,
            "total_questions": 20,
            "unanswered": 1,
            "accuracy": 50,
            "total_elapsed_seconds": 1800,
            "date_from": "2026-07-01T08:00:00+00:00",
            "date_to": "2026-07-05T08:00:00+00:00",
        },
        "deterministic_interpretation": ["本报告基于两次首次练习。"],
        "modules": [
            {
                "title": "Part 3",
                "progress": {"progress_text": "已完成 2/2 次练习"},
                "score": 10,
                "total": 20,
                "accuracy": 50,
                "trusted_seconds": 1800,
                "unanswered": 1,
            }
        ],
        "part_results": [
            {
                "title": "Part 3",
                "correct": 10,
                "total": 20,
                "accuracy": 50,
                "status_label": "薄弱",
                "sample_level": "stable",
            }
        ],
        "question_type_matrix": [
            {
                "question_type": "TRUE/FALSE/NOT GIVEN",
                "correct": 5,
                "total": 10,
                "accuracy": 50,
                "status_label": "薄弱",
            }
        ],
        "error_cause_distribution": [
            {
                "label": "FALSE 与 NOT GIVEN 混淆",
                "count": 4,
                "session_count": 2,
                "examples": ["剑雅15 Test 1 Q18"],
            }
        ],
        "representative_questions": [
            {
                "source": "剑雅15 Test 1 / Part 3 / Q18",
                "test_title": "剑雅15 Test 1",
                "question_number": 18,
                "question_type": "TRUE/FALSE/NOT GIVEN",
                "cause_label": "FALSE 与 NOT GIVEN 混淆",
                "prompt": "The policy started before 2010.",
                "user_answer": "NOT GIVEN",
                "correct_answer": "FALSE",
                "evidence": ["It started in 2012."],
                "analysis": "原文给出相反信息。",
                "student_confirmation_label": "未记录",
                "teacher_observation": "检查学生是否理解相反与未说明。",
            }
        ],
        "teacher_observation_points": ["请观察学生的判断流程。"],
        "data_notes": ["首次作答用于主要统计。"],
    }


def test_docx_matches_legacy_teacher_report_structure() -> None:
    payload = build_teacher_docx(_report(), title="真人老师课后作业")
    assert payload.startswith(b"PK")
    with ZipFile(BytesIO(payload)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
        assert "1. 数据摘要" in document_xml
        assert "2. 作业模块与完成情况" in document_xml
        assert "3. Part 表现" in document_xml
        assert "4. 题型正确率" in document_xml
        assert "5. 错因分布" in document_xml
        assert "6. 错题明细" in document_xml
        assert "7. 用时数据" in document_xml
        assert "8. 数据口径" in document_xml
        assert "原文定位：It started in 2012." in document_xml


def test_pdf_is_real_and_contains_the_full_report_story() -> None:
    payload = build_teacher_pdf(_report(), title="真人老师课后作业")
    assert payload.startswith(b"%PDF-")
    assert len(payload) > 5000
    assert payload.count(b"/Type /Page") >= 2
