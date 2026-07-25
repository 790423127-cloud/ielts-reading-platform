from __future__ import annotations

from app.domain.review import build_wrong_question_review, recommended_skill
from app.repositories.session_repository import StoredSession


def _session(
    session_id: str,
    created_at: str,
    *,
    correct: bool,
    subtype: str = "true_false_not_given",
    error_type: str | None = "incorrect",
) -> StoredSession:
    question = {
        "id": "b10-test-a-q1",
        "number": 1,
        "part_number": 1,
        "question_type": "判断题",
        "question_subtype": subtype,
        "prompt": "A review question",
        "user_answer": "FALSE" if not correct else "TRUE",
        "correct_answer": "TRUE",
        "is_correct": correct,
        "answer_error_type": None if correct else error_type,
        "analysis": "Review the scope.",
        "evidence": ["Verified evidence sentence."],
    }
    return StoredSession(
        id=session_id,
        user_id="owner",
        client_submission_id=f"client-{session_id}",
        test_id="b10-test-a",
        result={"question_results": [question]},
        created_at=created_at,
        idempotent_replay=False,
    )


def test_wrong_question_requires_two_consecutive_correct_answers_to_resolve() -> None:
    wrong = _session("s1", "2026-07-01T08:00:00+00:00", correct=False)
    first_correct = _session("s2", "2026-07-02T08:00:00+00:00", correct=True)
    second_correct = _session("s3", "2026-07-03T08:00:00+00:00", correct=True)

    after_wrong = build_wrong_question_review([wrong])
    assert len(after_wrong) == 1
    assert after_wrong[0]["wrong_count"] == 1
    assert after_wrong[0]["correct_streak_after_wrong"] == 0

    after_one_correct = build_wrong_question_review([wrong, first_correct])
    assert len(after_one_correct) == 1
    assert after_one_correct[0]["correct_streak_after_wrong"] == 1

    after_two_correct = build_wrong_question_review([wrong, first_correct, second_correct])
    assert after_two_correct == []


def test_new_wrong_after_resolution_reopens_review_and_resets_streak() -> None:
    sessions = [
        _session("s1", "2026-07-01T08:00:00+00:00", correct=False),
        _session("s2", "2026-07-02T08:00:00+00:00", correct=True),
        _session("s3", "2026-07-03T08:00:00+00:00", correct=True),
        _session("s4", "2026-07-04T08:00:00+00:00", correct=False),
    ]
    items = build_wrong_question_review(sessions)
    assert len(items) == 1
    assert items[0]["wrong_count"] == 2
    assert items[0]["correct_streak_after_wrong"] == 0
    assert items[0]["source_session_id"] == "s4"
    assert items[0]["method_course_id"] == "subtype-true_false_not_given"
    assert items[0]["recommended_skill_id"] == "scope-degree"


def test_error_and_subtype_route_to_exact_training_skill() -> None:
    assert recommended_skill("sentence_completion", "answer_span_too_long") == "answer-boundary"
    assert recommended_skill("summary_completion", "incorrect") == "spelling-plural"
    assert recommended_skill("matching_headings", "incorrect") == "main-detail"
    assert recommended_skill("matching_places", "incorrect") == "locating"
    assert recommended_skill("multiple_choice_single", "incorrect") == "paraphrase"
