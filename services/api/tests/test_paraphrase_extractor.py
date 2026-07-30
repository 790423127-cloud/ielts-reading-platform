from __future__ import annotations

import json

from app.repositories.vocabulary_repository import VocabularyRepository
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
