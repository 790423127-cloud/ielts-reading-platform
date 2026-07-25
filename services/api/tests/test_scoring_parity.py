from __future__ import annotations

from app.domain.scoring import score_submission


def test_scoring_result_keeps_post_submit_review_fields() -> None:
    test = {
        "id": "fixture-test",
        "title": "Fixture Test",
        "parts": [
            {
                "number": 1,
                "title": "Part 1",
                "groups": [
                    {
                        "question_type": "true_false_not_given",
                        "question_label": "判断题",
                        "instructions": "Do the statements agree?",
                        "questions": [
                            {
                                "id": "q1",
                                "number": 1,
                                "prompt": "The service opens daily.",
                                "answer": "TRUE",
                                "accepted_answers": ["TRUE"],
                                "evidence": ["The service is open seven days a week."],
                            }
                        ],
                    },
                    {
                        "question_type": "form_completion",
                        "question_label": "表格填空",
                        "instructions": "NO MORE THAN TWO WORDS AND/OR A NUMBER",
                        "questions": [
                            {
                                "id": "q2",
                                "number": 2,
                                "prompt": "Minimum age: ____",
                                "answer": "21",
                                "accepted_answers": ["21"],
                            }
                        ],
                    },
                ],
            },
            {
                "number": 2,
                "title": "Part 2",
                "groups": [
                    {
                        "question_type": "multiple_choice_multiple",
                        "question_label": "多选题",
                        "required_choices": 2,
                        "instructions": "Choose TWO letters.",
                        "questions": [
                            {
                                "id": "q3",
                                "number": 3,
                                "prompt": "Which TWO facilities are included?",
                                "answer": "B, D",
                                "accepted_answers": ["B", "D"],
                            }
                        ],
                    },
                    {
                        "question_type": "sentence_completion",
                        "question_label": "句子填空",
                        "instructions": "NO MORE THAN TWO WORDS",
                        "questions": [
                            {
                                "id": "q4",
                                "number": 4,
                                "prompt": "Students need ____.",
                                "answer": "student accommodation",
                                "accepted_answers": ["student accommodation"],
                                "analysis": "The answer is the shortest complete noun phrase.",
                            }
                        ],
                    },
                ],
            },
        ],
    }

    result = score_submission(
        test,
        {
            "q1": "T",
            "q2": "twenty one",
            "q3": "D B",
            "q4": "accommodation",
        },
        exam_mode="study",
        total_elapsed_seconds=240,
    )

    assert result["score"] == 3
    assert result["total"] == 4
    assert result["accuracy"] == 75.0
    assert result["unanswered_count"] == 0
    assert result["band_estimate"]["eligible"] is False
    assert len(result["wrong_questions"]) == 1
    wrong = result["wrong_questions"][0]
    assert wrong["id"] == "q4"
    assert wrong["answer_error_type"] == "answer_span_too_short"
    assert wrong["correct_answer"] == "student accommodation"
    assert result["part_results"] == [
        {"part_number": 1, "title": "Part 1", "score": 2, "total": 2, "accuracy": 100.0},
        {"part_number": 2, "title": "Part 2", "score": 1, "total": 2, "accuracy": 50.0},
    ]


def test_only_complete_40_question_submission_gets_band() -> None:
    questions = [
        {
            "id": f"q{number}",
            "number": number,
            "prompt": f"Question {number}",
            "answer": "A",
            "accepted_answers": ["A"],
        }
        for number in range(1, 41)
    ]
    test = {
        "id": "full-40",
        "title": "Full GT Reading",
        "parts": [
            {
                "number": 1,
                "title": "Complete test",
                "groups": [
                    {
                        "question_type": "multiple_choice_single",
                        "question_label": "单选题",
                        "instructions": "Choose ONE letter.",
                        "questions": questions,
                    }
                ],
            }
        ],
    }
    answers = {
        f"q{number}": "A" if number <= 30 else "B"
        for number in range(1, 41)
    }

    result = score_submission(test, answers, exam_mode="mock_exam")

    assert result["score"] == 30
    assert result["total"] == 40
    assert result["estimated_gt_reading_band"] == 6.0
    assert result["band_estimate"]["eligible"] is True
