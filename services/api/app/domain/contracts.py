from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


ExamMode = Literal["study", "part_practice", "question_type", "ability", "mock_exam"]
SessionStatus = Literal["created", "in_progress", "submitted", "abandoned"]


class PublicQuestion(BaseModel):
    """Question payload allowed before submission. It intentionally has no answer key."""

    model_config = ConfigDict(extra="forbid")

    id: str
    number: int = Field(ge=1)
    prompt: str
    question_type: str
    subtype: str
    instructions: str | None = None
    options: list[str] = Field(default_factory=list)


class SubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_submission_id: str = Field(min_length=8, max_length=160)
    answers: dict[str, str | list[str]]
    elapsed_seconds: int = Field(ge=0)


class BandEstimate(BaseModel):
    eligible: bool
    raw_score: int = Field(ge=0)
    out_of: int = Field(ge=1)
    estimated_band: float | None = None
    display_band: str | None = None
    next_band: float | None = None
    next_band_minimum_score: int | None = None
    questions_to_next_band: int | None = None
    is_official_result: bool = False
    notice_zh: str | None = None
    version: str | None = None


class SubmittedQuestionReview(BaseModel):
    question_id: str
    correct: bool
    user_answer: str | list[str] | None
    correct_answer: str | list[str]
    evidence: list[str]
    explanation: str | None = None


class SubmissionResult(BaseModel):
    session_id: str
    correct_count: int = Field(ge=0)
    total_questions: int = Field(ge=1)
    band: float | None
    band_estimate: BandEstimate | None = None
    reviews: list[SubmittedQuestionReview]
