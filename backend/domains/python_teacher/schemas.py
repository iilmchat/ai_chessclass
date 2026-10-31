"""DTO python-домена: pythonic-поля + CamelModel (JSON — camelCase)."""

from datetime import datetime

from pydantic import Field

from core.base import CamelModel
from domains.python_teacher.models import AssignmentLevel, Verdict


class AssignmentOut(CamelModel):
    id: str
    slug: str
    title: str
    level: AssignmentLevel
    topic: str
    tests_count: int  # JSON: testsCount


class AssignmentDetailOut(AssignmentOut):
    statement: str
    starter_code: str  # JSON: starterCode
    # tests/checkpoints — только для admin (ученику тесты не отдаём)
    tests: list[str] | None = None
    checkpoints: list | None = None
    is_active: bool | None = None


class HintIn(CamelModel):
    idx: int = Field(ge=0, le=9)
    kind: str = Field(pattern=r"^(concept|strategy|pseudocode|code)$")
    content: str = Field(min_length=3, max_length=4000)


class AssignmentCreateIn(CamelModel):
    slug: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9-]+$")
    title: str = Field(min_length=3, max_length=200)
    level: AssignmentLevel
    topic: str = Field(min_length=2, max_length=64)
    statement: str = Field(min_length=10)
    starter_code: str = Field(default="", max_length=8000)
    tests: list[str] = Field(min_length=1, max_length=50)
    hints: list[HintIn] | None = None


class AssignmentUpdateIn(CamelModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    level: AssignmentLevel | None = None
    statement: str | None = Field(default=None, min_length=10)
    starter_code: str | None = Field(default=None, max_length=8000)
    tests: list[str] | None = Field(default=None, min_length=1, max_length=50)


class SubmitIn(CamelModel):
    code: str = Field(min_length=1, max_length=20000)


class HintOut(CamelModel):
    idx: int
    kind: str
    content: str
    source: str  # seeded | llm


class SolutionOut(CamelModel):
    source: str
    note: str | None


class FeedbackOut(CamelModel):
    content: str
    model_used: str  # JSON: modelUsed
    level: str


class SubmissionOut(CamelModel):
    id: str
    assignment_id: str  # JSON: assignmentId
    verdict: Verdict
    passed_tests: int  # JSON: passedTests
    total_tests: int  # JSON: totalTests
    failed_test: int | None  # JSON: failedTest
    stdout_digest: str | None  # JSON: stdoutDigest
    duration_ms: int | None  # JSON: durationMs
    created_at: datetime  # JSON: createdAt
    feedback: FeedbackOut | None = None


class HintRequestIn(CamelModel):
    hint_idx: int = Field(ge=0, le=19)  # JSON: hintIdx
