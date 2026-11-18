from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class LeadCaptureRecord(BaseModel):
    """Validated recruiter/visitor lead persisted before Pushover dispatch."""

    email: str
    name: str = "Not provided"
    notes: str = "Not provided"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip()
        if not EMAIL_PATTERN.match(cleaned):
            raise ValueError(f"Malformed email address: {value!r}")
        return cleaned


class KnowledgeGapRecord(BaseModel):
    """Logged unsupported or ungrounded question."""

    question: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Question cannot be empty.")
        return cleaned


class TwinChatResponse(BaseModel):
    """Structured output returned by CareerConciergeEngine.chat."""

    reply: str
    tool_calls_made: List[str] = Field(default_factory=list)
    tool_rounds: int = 0
    terminated_by_limit: bool = False
    recorded_leads: List[LeadCaptureRecord] = Field(default_factory=list)
    recorded_unknown_questions: List[KnowledgeGapRecord] = Field(default_factory=list)
