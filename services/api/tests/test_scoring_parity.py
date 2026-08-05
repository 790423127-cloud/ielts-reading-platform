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
        {"part_number": 1, "title": "Part 1", "score": 2, "total": 2, "accuracy": 100.0, "elapsed_seconds": 0},
        {"part_number": 2, "title": "Part 2", "score": 1, "total": 2, "accuracy": 50.0, "elapsed_seconds": 0},
    ]


def test_question_level_required_choices_supports_two_answers_inside_a_mixed_group() -> None:
    test = {
        "id": "mixed-matching",
        "title": "Mixed matching answers",
        "parts": [{
            "number": 1,
            "groups": [{
                "question_type": "matching_information",
                "question_label": "信息匹配",
                "instructions": "Write the correct letter A-G.",
                "questions": [
                    {
                        "id": "q8",
                        "number": 8,
                        "prompt": "One programme",
                        "answer": "D",
                        "accepted_answers": ["D"],
                    },
                    {
                        "id": "q10",
                        "number": 10,
                        "prompt": "These TWO programmes",
                        "answer": "C and E",
                        "accepted_answers": ["C and E", "C E", "C, E"],
                        "required_choices": 2,
                    },
                ],
            }],
        }],
    }

    result = score_submission(
        test,
        {"q8": "D", "q10": "E C"},
        exam_mode="study",
    )

    assert result["score"] == 2
    assert result["question_results"][1]["is_correct"] is True


def test_shared_multiple_choice_awards_one_mark_for_each_correct_selection() -> None:
    questions = [
        {
            "id": f"q{number}",
            "number": number,
            "prompt": "Which FOUR qualities are mentioned?",
            "answer": "D,E,F,I",
            "accepted_answers": ["D,E,F,I"],
            "required_choices": 4,
        }
        for number in range(33, 37)
    ]
    test = {
        "id": "shared-multiple",
        "title": "Shared multiple choice",
        "parts": [{
            "number": 3,
            "title": "Part 3",
            "groups": [{
                "question_type": "multiple_choice_multiple",
                "question_label": "多选题",
                "required_choices": 4,
                "shared_response": True,
                "instructions": "Choose FOUR letters A-J.",
                "questions": questions,
            }],
        }],
    }

    result = score_submission(
        test,
        {question["id"]: ["A", "D", "F", "H"] for question in questions},
        exam_mode="study",
    )

    assert result["score"] == 2
    assert result["total"] == 4
    assert result["accuracy"] == 50.0
    assert len(result["wrong_questions"]) == 2
    assert result["unanswered_count"] == 0
    assert [row["is_correct"] for row in result["question_results"]] == [False, True, True, False]
    summary = result["question_results"][0]
    assert summary["shared_response_score"] == 2
    assert summary["shared_response_total"] == 4
    assert summary["selected_correct_answers"] == ["D", "F"]
    assert summary["selected_incorrect_answers"] == ["A", "H"]
    assert summary["missed_correct_answers"] == ["E", "I"]


def test_shared_multiple_choice_counts_missing_slots_as_unanswered() -> None:
    questions = [
        {"id": f"q{number}", "number": number, "answer": "A,C", "accepted_answers": ["A,C"]}
        for number in (1, 2)
    ]
    test = {
        "id": "shared-multiple-incomplete",
        "parts": [{
            "number": 1,
            "groups": [{
                "question_type": "multiple_choice_multiple",
                "required_choices": 2,
                "shared_response": True,
                "questions": questions,
            }],
        }],
    }

    result = score_submission(test, {"q1": ["A"], "q2": ["A"]}, exam_mode="study")

    assert result["score"] == 1
    assert result["unanswered_count"] == 1


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
