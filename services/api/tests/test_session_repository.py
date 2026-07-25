from __future__ import annotations

from app.repositories.session_repository import SQLiteSessionRepository


def result_fixture(score: int = 3) -> dict:
    return {
        "test_id": "fixture-test",
        "test_title": "Fixture Test",
        "score": score,
        "total": 4,
        "accuracy": score / 4 * 100,
        "question_results": [],
        "wrong_questions": [],
        "band_estimate": {"eligible": False, "raw_score": score, "out_of": 4},
    }


def test_same_user_and_client_submission_id_is_idempotent(tmp_path) -> None:
    repository = SQLiteSessionRepository(tmp_path / "progress.db")

    first = repository.save_or_get(
        user_id="admin-user",
        client_submission_id="submission-0001",
        test_id="fixture-test",
        result=result_fixture(3),
    )
    replay = repository.save_or_get(
        user_id="admin-user",
        client_submission_id="submission-0001",
        test_id="fixture-test",
        result=result_fixture(1),
    )

    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.id == first.id
    assert replay.result["score"] == 3


def test_same_client_submission_id_is_isolated_by_user(tmp_path) -> None:
    repository = SQLiteSessionRepository(tmp_path / "progress.db")

    first_user = repository.save_or_get(
        user_id="user-a",
        client_submission_id="submission-shared",
        test_id="fixture-test",
        result=result_fixture(3),
    )
    second_user = repository.save_or_get(
        user_id="user-b",
        client_submission_id="submission-shared",
        test_id="fixture-test",
        result=result_fixture(2),
    )

    assert first_user.id != second_user.id
    assert first_user.result["score"] == 3
    assert second_user.result["score"] == 2


def test_user_cannot_read_another_users_session(tmp_path) -> None:
    repository = SQLiteSessionRepository(tmp_path / "progress.db")
    stored = repository.save_or_get(
        user_id="user-a",
        client_submission_id="submission-private",
        test_id="fixture-test",
        result=result_fixture(),
    )

    assert repository.get(user_id="user-a", session_id=stored.id) is not None
    assert repository.get(user_id="user-b", session_id=stored.id) is None
