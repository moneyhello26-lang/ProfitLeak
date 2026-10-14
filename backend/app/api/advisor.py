from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import Database, require_business
from app.core.config import Settings, get_settings
from app.schemas.advisor import AdvisorRequest, AdvisorResponse, AdvisorStatus
from app.schemas.imports import ErrorResponse
from app.services import advisor
from app.services.analytics import resolve_period

router = APIRouter(prefix="/api/v1/advisor", tags=["Advisor"])
Configuration = Annotated[Settings, Depends(get_settings)]


@router.get("/status", response_model=AdvisorStatus)
def connection_status(settings: Configuration):
    return advisor.status(settings)


@router.post(
    "/chat",
    response_model=AdvisorResponse,
    responses={code: {"model": ErrorResponse} for code in (400, 404)},
)
def chat(db: Database, settings: Configuration, request: AdvisorRequest):
    business = require_business(db, request.business_id)
    period = resolve_period(db, business, request.date_from, request.date_to)
    ctx = advisor.context(db, business.id, period, request.insight_id)
    # End the read transaction before waiting on a network service (especially on SQLite).
    db.commit()
    return advisor.respond(settings, request, ctx)
