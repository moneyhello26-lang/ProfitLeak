from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.analytics import SelectedPeriod
from app.api.dependencies import Database, require_business
from app.schemas.imports import ErrorResponse
from app.schemas.insights import (
    AnalysisRead,
    AnalysisRequest,
    InsightRead,
    InsightsRead,
    InsightType,
    Severity,
)
from app.services import insights
from app.services.analytics import resolve_period

router = APIRouter(prefix="/api/v1", tags=["Insights"])
ERRORS = {status: {"model": ErrorResponse} for status in (400, 404)}


@router.post("/analysis/run", response_model=AnalysisRead, responses=ERRORS)
def analyze(db: Database, request: AnalysisRequest):
    business = require_business(db, request.business_id)
    period = resolve_period(db, business, request.date_from, request.date_to)
    result = insights.run_analysis(db, business.id, period)
    db.commit()
    return result


@router.get("/insights", response_model=InsightsRead, responses=ERRORS)
def insight_list(
    db: Database,
    business_id: UUID,
    period: SelectedPeriod,
    severity: Severity | None = None,
    insight_type: Annotated[InsightType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return insights.list_insights(db, business_id, period, severity, insight_type, limit, offset)


@router.get("/insights/{insight_id}", response_model=InsightRead, responses=ERRORS)
def insight_detail(db: Database, business_id: UUID, insight_id: UUID):
    require_business(db, business_id)
    return insights.insight_detail(db, business_id, insight_id)
