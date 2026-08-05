from __future__ import annotations

import json

from app.repositories.vocabulary_repository import VocabularyRepository
from app.services.ai_teacher import AiTeacherProviderError
from app.services.paraphrase_extractor import extract_wrong_question_paraphrases


def _result() -> dict:
    wrong = {
        "id": "q2",
        "number": 2,
        "part_number": 1,
        "question_type": "TRUE/FALSE/NOT GIVEN",
        "prompt": "Men's silk shirts are available in more than five colours.",
        "instructions": "Choose TRUE if the statement agrees with the information.",
        "options": [],
        "user_answer": "FALSE",
        "correct_answer": "NOT GIVEN",
        "is_correct": False,
        "evidence": ["Silk shirts M - five sizes, in designer colours, for that special social occasion"],
    }
    correct = {
        "id": "q1",
        "number": 1,
        "part_number": 1,
        "prompt": "Women's cotton socks cost less than men's.",
        "user_answer": "NOT GIVEN",
        "correct_answer": "NOT GIVEN",
        "is_correct": True,
        "evidence": ["Cotton socks C - made of pure cotton for long wearing"],
    }
    return {
        "test_id": "g5-test-a",
        "test_title": "剑雅5 Test A",
        "question_results": [correct, wrong],
        "wrong_questions": [wrong],
    }


def test_ai_records_only_wrong_question_prompt_to_evidence_pairs(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")

    def fake_ai(**_: object) -> dict:
        return {
            "answer": json.dumps(
                {
                    "items": [
                        {
                            "question_id": "q2",
                            "question_phrase": "more than five colours",
                            "source_phrase": "designer colours",
                            "note": "题目问颜色数量，原文只说 designer colours，没有给出 more than five。",
                            "confidence": 0.91,
                        },
                        {
                            "question_id": "q1",
                            "question_phrase": "cost less than",
                            "source_phrase": "under $10",
                            "note": "这是正确题，不应保存。",
                            "confidence": 0.95,
                        },
                    ]
                },
                ensure_ascii=False,
            )
        }

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-1",
        result=_result(),
        ai_reply_generator=fake_ai,
    )

    assert summary["status"] == "completed"
    assert summary["candidate_count"] == 2
    assert summary["saved_count"] == 1
    items = repository.list_paraphrases(user_id="owner")
    assert len(items) == 1
    assert items[0]["question_phrase"] == "more than five colours"
    assert items[0]["source_phrase"] == "designer colours"
    assert items[0]["sources"][0]["source_question_id"] == "q2"


def test_ai_candidate_must_exist_in_question_and_evidence(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")

    def fake_ai(**_: object) -> dict:
        return {
            "answer": json.dumps(
                {
                    "items": [
                        {
                            "question_id": "q2",
                            "question_phrase": "colour question",
                            "source_phrase": "designer colours",
                            "note": "question_phrase 不在题目里，跳过。",
                            "confidence": 0.95,
                        },
                        {
                            "question_id": "q2",
                            "question_phrase": "more than five colours",
                            "source_phrase": "many different colours",
                            "note": "source_phrase 不在原文证据里，跳过。",
                            "confidence": 0.95,
                        },
                    ]
                },
                ensure_ascii=False,
            )
        }

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-1",
        result=_result(),
        ai_reply_generator=fake_ai,
    )

    assert summary["saved_count"] == 0
    assert summary["skipped_count"] == 2
    assert repository.list_paraphrases(user_id="owner") == []


def test_curated_paraphrase_is_saved_without_calling_ai(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")
    result = _result()
    result["wrong_questions"][0]["paraphrasing"] = (
        "more than five colours -> designer colours"
    )

    def unexpected_ai(**_: object) -> dict:
        raise AssertionError("curated data should not call AI")

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-local",
        result=result,
        ai_reply_generator=unexpected_ai,
    )

    assert summary["status"] == "completed"
    assert summary["local_saved_count"] == 1
    assert summary["ai_saved_count"] == 0
    assert summary["ai_status"] == "not_needed"
    items = repository.list_paraphrases(user_id="owner")
    assert [(item["question_phrase"], item["source_phrase"]) for item in items] == [
        ("more than five colours", "designer colours")
    ]


def test_ai_failure_keeps_curated_paraphrases(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")
    result = _result()
    first = result["wrong_questions"][0]
    first["paraphrasing"] = "more than five colours -> designer colours"
    unresolved = {
        **first,
        "id": "q3",
        "number": 3,
        "prompt": "Which shirts are suitable for a celebration?",
        "paraphrasing": "",
    }
    result["wrong_questions"].append(unresolved)

    def failed_ai(**_: object) -> dict:
        raise AiTeacherProviderError("provider returned no visible text")

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-partial",
        result=result,
        ai_reply_generator=failed_ai,
    )

    assert summary["status"] == "partial"
    assert summary["local_saved_count"] == 1
    assert summary["ai_saved_count"] == 0
    assert summary["ai_status"] == "failed"
    assert len(repository.list_paraphrases(user_id="owner")) == 1


def test_local_phase_queues_ai_without_calling_provider(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")

    def unexpected_ai(**_: object) -> dict:
        raise AssertionError("local phase must not call AI")

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-queued",
        result=_result(),
        ai_reply_generator=unexpected_ai,
        allow_ai=False,
    )

    assert summary["status"] == "queued"
    assert summary["ai_status"] == "queued"
    assert summary["saved_count"] == 0


def test_duplicate_ai_candidates_are_counted_once(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")
    candidate = {
        "question_id": "q2",
        "question_phrase": "more than five colours",
        "source_phrase": "designer colours",
        "note": "同一候选被模型重复返回。",
        "confidence": 0.91,
    }

    def duplicate_ai(**_: object) -> dict:
        return {"answer": json.dumps({"items": [candidate, candidate]})}

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="session-duplicate",
        result=_result(),
        ai_reply_generator=duplicate_ai,
    )

    assert summary["saved_count"] == 1
    assert summary["ai_saved_count"] == 1
    assert summary["deduplicated_candidate_count"] == 1
    assert len(repository.list_paraphrases(user_id="owner")) == 1


def test_curated_phrase_allows_small_ordered_gap_in_evidence(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")
    question = {
        "id": "q32",
        "number": 32,
        "part_number": 3,
        "prompt": "glow-worm caves have attracted millions of people",
        "evidence": [
            "The glow-worm caves in New Zealand have attracted millions of people."
        ],
        "paraphrasing": (
            "glow-worm caves have attracted -> "
            "glow-worm caves in New Zealand have attracted"
        ),
    }
    result = {
        "test_id": "gap-test",
        "test_title": "Gap test",
        "wrong_questions": [question],
    }

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="gap-session",
        result=result,
    )

    assert summary["local_saved_count"] == 1
    assert summary["ai_status"] == "not_needed"


def test_long_or_logical_ai_candidates_are_rejected(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")

    def fake_ai(**_: object) -> dict:
        return {
            "answer": json.dumps(
                {
                    "items": [
                        {
                            "question_id": "q2",
                            "question_phrase": "Men's silk shirts are available in more than five colours",
                            "source_phrase": "Silk shirts in five sizes in designer colours",
                            "relation_type": "direct-paraphrase",
                            "confidence": 0.95,
                        },
                        {
                            "question_id": "q2",
                            "question_phrase": "more than five colours",
                            "source_phrase": "designer colours",
                            "relation_type": "logical-contrast",
                            "confidence": 0.95,
                        },
                    ]
                }
            )
        }

    summary = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="rejected-session",
        result=_result(),
        ai_reply_generator=fake_ai,
    )

    assert summary["saved_count"] == 0
    assert summary["skipped_count"] == 2


def test_ai_processes_all_allowed_batches_and_reports_deferred(tmp_path) -> None:
    repository = VocabularyRepository(tmp_path / "sessions.sqlite3")
    wrong_questions = []
    for number in range(1, 11):
        wrong_questions.append(
            {
                "id": f"q{number}",
                "number": number,
                "part_number": 1,
                "prompt": f"Item {number} costs less than ten dollars.",
                "evidence": [f"Item {number} is under $10."],
                "paraphrasing": "",
            }
        )
    result = {
        "test_id": "batch-test",
        "test_title": "Batch test",
        "wrong_questions": wrong_questions,
    }
    call_sizes: list[int] = []

    def fake_ai(**kwargs: object) -> dict:
        context = kwargs["context"]
        assert isinstance(context, dict)
        batch = context["wrong_questions"]
        assert isinstance(batch, list)
        call_sizes.append(len(batch))
        items = [
            {
                "question_id": row["id"],
                "question_phrase": "costs less than ten dollars",
                "source_phrase": "under $10",
                "relation_type": "near-paraphrase",
                "confidence": 0.9,
            }
            for row in batch
        ]
        return {"answer": json.dumps({"items": items})}

    complete = extract_wrong_question_paraphrases(
        repository=repository,
        user_id="owner",
        session_id="batch-complete",
        result=result,
        ai_reply_generator=fake_ai,
        max_ai_calls=2,
    )
    assert call_sizes == [8, 2]
    assert complete["ai_batches_completed"] == 2
    assert complete["ai_deferred_question_count"] == 0

    call_sizes.clear()
    limited = extract_wrong_question_paraphrases(
        repository=VocabularyRepository(tmp_path / "limited.sqlite3"),
        user_id="owner",
        session_id="batch-limited",
        result=result,
        ai_reply_generator=fake_ai,
        max_ai_calls=1,
    )
    assert call_sizes == [8]
    assert limited["status"] == "partial"
    assert limited["ai_deferred_question_count"] == 2
