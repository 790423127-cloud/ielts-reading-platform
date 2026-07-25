from app.domain.contracts import PublicQuestion, SubmissionResult


def test_public_question_cannot_leak_answer_fields() -> None:
    fields = set(PublicQuestion.model_fields)
    forbidden = {"answer", "correct_answer", "explanation", "evidence", "analysis"}
    assert fields.isdisjoint(forbidden)


def test_band_is_nullable_until_full_mock_rule_is_migrated() -> None:
    result = SubmissionResult(
        session_id="session-1",
        correct_count=3,
        total_questions=8,
        band=None,
        reviews=[],
    )
    assert result.band is None
