from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analytics import Period

InsightType = Literal[
    "EXPENSE_SPIKE", "MARGIN_DROP", "LOW_PROFIT_PRODUCT", "SALES_DROP", "POSSIBLE_DUPLICATE"
]
Severity = Literal["low", "medium", "high"]
WorkflowStatus = Literal["new", "in_progress", "reviewed", "dismissed"]


class InsightWorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: WorkflowStatus
    note: str = Field(max_length=2000)


class AnalysisRequest(BaseModel):
    business_id: UUID
    date_from: date | None = None
    date_to: date | None = None


class RuleCheck(BaseModel):
    type: InsightType
    status: Literal["evaluated", "insufficient_data"]
    signals: int
    reason: str
    skipped_entities: int = 0


class SourceRow(BaseModel):
    record_id: UUID
    import_id: UUID
    filename: str
    source_row: int
    date: date
    record_type: str
    amount: Decimal


class InsightEvidence(BaseModel):
    title: str
    explanation: str
    entity: str
    current_period: Period
    baseline_period: Period | None = None
    current_value: Decimal
    baseline_value: Decimal | None = None
    value_unit: Literal["KZT", "percent"] = "KZT"
    deviation_percent: Decimal | None = None
    deviation_pp: Decimal | None = None
    threshold: Decimal | None = None
    formula: str
    current_rows: int
    baseline_rows: int = 0
    current_days: int
    baseline_days: int = 0
    source_rows: list[SourceRow]
    source_rows_total: int
    caveat: str
    savings_assumption: str | None = None
    product_id: UUID | None = None
    category: str | None = None
    current_revenue: Decimal | None = None
    current_cogs: Decimal | None = None
    baseline_revenue: Decimal | None = None
    baseline_cogs: Decimal | None = None


class InsightRead(BaseModel):
    id: UUID
    business_id: UUID
    type: InsightType
    severity: Severity
    confidence: Severity
    period: Period
    evidence: InsightEvidence
    potential_savings_kzt: Decimal | None
    estimate_type: Literal["scenario"] | None
    recommendation: str
    recommendation_source: Literal["template"] = "template"
    created_at: datetime
    workflow_status: WorkflowStatus = "new"
    workflow_note: str = ""
    workflow_updated_at: datetime | None = None


class AnalysisRead(BaseModel):
    id: UUID
    business_id: UUID
    period: Period
    current_period: Period | None
    baseline_period: Period | None
    analyzed_at: datetime
    rules_version: str
    insight_count: int
    checks: list[RuleCheck]
    stale: bool = False


class InsightsRead(BaseModel):
    business_id: UUID
    period: Period
    analysis: AnalysisRead | None
    items: list[InsightRead]
    total: int
    limit: int
    offset: int
