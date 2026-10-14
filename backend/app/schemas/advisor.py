from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.analytics import Period

FallbackReason = Literal[
    "disabled",
    "missing_key",
    "consent_required",
    "timeout",
    "connection_error",
    "authentication_error",
    "rate_limit",
    "quota_exhausted",
    "model_error",
    "provider_error",
    "invalid_response",
]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class AdvisorRequest(BaseModel):
    business_id: UUID
    date_from: date | None = None
    date_to: date | None = None
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)
    insight_id: UUID | None = None
    allow_external: bool = False
    external_provider: Literal["openai", "gemini"] | None = None

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Введите вопрос")
        return value.strip()


class AdvisorStatus(BaseModel):
    enabled: bool
    ready: bool
    provider: Literal["openai", "gemini"] = "openai"
    model: str
    fallback_reason: FallbackReason | None


class AdvisorFact(BaseModel):
    id: str
    label: str
    value: str
    source: Literal["summary", "insight"]
    insight_id: UUID | None = None


class AdvisorResponse(BaseModel):
    business_id: UUID
    period: Period
    answer: str
    source: Literal["llm", "template"]
    model: str | None = None
    provider: Literal["openai", "gemini"] | None = None
    cached: bool = False
    retry_after_seconds: int | None = None
    fallback_reason: FallbackReason | None = None
    facts: list[AdvisorFact]
    analysis_status: Literal["not_run", "current", "stale"]
    disclaimer: str = "Сигналы и сценарные оценки требуют проверки; экономия не гарантируется."
