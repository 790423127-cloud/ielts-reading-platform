"""Read-only full-bank audit for wrong-question paraphrase extraction.

The script never calls an AI provider and never opens the session database.
It scores each available test with blank answers, then applies the same local
phrase validation used by the production extractor.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
sys.path.insert(0, str(API_ROOT))

from app.domain.scoring import score_submission  # noqa: E402
from app.services.paraphrase_extractor import (  # noqa: E402
    MAX_AI_WRONG_QUESTIONS,
    _curated_pairs,
    _pair_validation_reason,
    _phrase_word_count,
    _wrong_question_payload,
)
from app.services.question_bank import QuestionBank, expected_test_index  # noqa: E402


def main() -> None:
    bank = QuestionBank(API_ROOT / "data" / "question-bank")
    totals: Counter[str] = Counter()
    per_test: list[dict[str, int | str]] = []

    for index_item in expected_test_index():
        test_id = str(index_item["id"])
        if not (bank.test_dir / f"{test_id}.json").is_file():
            continue
        test = bank.load_server_test(test_id)
        result = score_submission(test, {}, exam_mode="mock_exam")
        wrong_questions = _wrong_question_payload(result)
        accepted_questions = 0
        unresolved_questions = 0
        rejection_counts: Counter[str] = Counter()

        for question in wrong_questions:
            pairs = _curated_pairs(question.get("paraphrasing"))
            accepted_for_question = 0
            totals["curated_candidates"] += len(pairs)
            for question_phrase, source_phrase in pairs:
                if max(
                    _phrase_word_count(question_phrase),
                    _phrase_word_count(source_phrase),
                ) > 8:
                    totals["over_eight_word_candidates"] += 1
                reason = _pair_validation_reason(
                    question, question_phrase, source_phrase
                )
                if reason:
                    rejection_counts[reason] += 1
                    totals[f"rejected_{reason}"] += 1
                    continue
                totals["accepted_pairs"] += 1
                accepted_for_question += 1
            if accepted_for_question:
                accepted_questions += 1
            else:
                unresolved_questions += 1

        totals["tests"] += 1
        totals["questions"] += len(result.get("question_results") or [])
        totals["wrong_questions"] += len(wrong_questions)
        totals["locally_resolved_questions"] += accepted_questions
        totals["ai_unresolved_questions"] += unresolved_questions
        totals["ai_batches_needed"] += (
            unresolved_questions + MAX_AI_WRONG_QUESTIONS - 1
        ) // MAX_AI_WRONG_QUESTIONS
        per_test.append(
            {
                "test_id": test_id,
                "wrong_questions": len(wrong_questions),
                "locally_resolved_questions": accepted_questions,
                "ai_unresolved_questions": unresolved_questions,
                "ai_batches_needed": (
                    unresolved_questions + MAX_AI_WRONG_QUESTIONS - 1
                ) // MAX_AI_WRONG_QUESTIONS,
                **dict(rejection_counts),
            }
        )

    report = {
        "mode": "read_only_no_ai_no_database",
        "totals": dict(totals),
        "tests_with_ai_unresolved": sum(
            1 for row in per_test if int(row["ai_unresolved_questions"]) > 0
        ),
        "max_ai_unresolved_in_one_test": max(
            (int(row["ai_unresolved_questions"]) for row in per_test),
            default=0,
        ),
        "per_test": per_test,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
