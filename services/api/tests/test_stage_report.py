from __future__ import annotations

from app.domain.stage_report import build_stage_report
from app.repositories.session_repository import StoredSession


def _session(
    session_id: str,
    created_at: str,
    *,
    score: int,
    test_id: str = "b10-test-a",
) -> StoredSession:
    questions = [
        {
            "id": f"{test_id}-q{number}",
            "source_question_id": f"{test_id}-q{number}",
            "number": number,
            "part_number": 1,
            "source_part_number": 1,
            "source_test_id": test_id,
            "question_type": "TRUE/FALSE/NOT GIVEN",
            "question_subtype": "true_false_not_given",
            "is_correct": number <= score,
            "prompt": f"Question {number}",
            "user_answer": "TRUE" if number <= score else "FALSE",
            "correct_answer": "TRUE",
            "elapsed_seconds": number * 10,
            "evidence": ["Verified evidence."],
            "analysis": "Check scope.",
        }
        for number in range(1, 11)
    ]
    result = {
        "test_id": test_id,
        "test_title": test_id,
        "practice_mode": "part_practice",
        "part_numbers": [1],
        "score": score,
        "total": 10,
        "accuracy": score * 10.0,
        "total_elapsed_seconds": 600,
        "question_results": questions,
        "wrong_questions": [item for item in questions if not item["is_correct"]],
    }
    return StoredSession(
        id=session_id,
        user_id="owner",
        client_submission_id=f"client-{session_id}",
        test_id=test_id,
        result=result,
        created_at=created_at,
        idempotent_replay=False,
    )


def test_stage_report_is_deterministic_and_separates_retries() -> None:
    report = build_stage_report(
        [
            _session("s1", "2026-07-01T08:00:00+00:00", score=4),
            _session("s2", "2026-07-02T08:00:00+00:00", score=7),
        ]
    )
    assert report["ai_calls"] == 0
    assert report["summary"]["session_count"] == 2
    assert report["summary"]["first_attempt_count"] == 1
    assert report["summary"]["retry_count"] == 1
    assert report["summary"]["accuracy"] == 55.0
    assert report["question_type_matrix"][0]["status"] == "weak"
    assert report["question_type_matrix"][0]["sample_level"] == "stable"
    assert report["representative_questions"][0]["source_question_ref"].startswith(
        "b10-test-a:1:"
    )
    assert len(report["slowest_correct_questions"]) == 3
    assert len(report["slowest_wrong_questions"]) == 5
    assert [
        item["elapsed_seconds"] for item in report["slowest_correct_questions"]
    ] == [70, 60, 50]
    assert [
        item["elapsed_seconds"] for item in report["slowest_wrong_questions"]
    ] == [100, 90, 80, 70, 60]
    assert report["deterministic_interpretation"]


def test_empty_stage_report_is_explicit_and_safe() -> None:
    report = build_stage_report([])
    assert report["summary"]["session_count"] == 0
    assert report["summary"]["accuracy"] == 0.0
    assert report["trend"] == []
    assert report["representative_questions"] == []
    assert report["slowest_correct_questions"] == []
    assert report["slowest_wrong_questions"] == []
