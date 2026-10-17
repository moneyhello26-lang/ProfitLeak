from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.analytics import SelectedPeriod
from app.api.dependencies import Database, require_business
from app.schemas.analytics import Period
from app.schemas.imports import ErrorResponse
from app.schemas.planning import FinancialForecast, PeriodComparison
from app.services import analytics, comparison, forecast

router = APIRouter(prefix="/api/v1/analytics", tags=["Planning"])
ERRORS = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


@router.get("/comparison", response_model=PeriodComparison, responses=ERRORS)
def compare_periods(
    db: Database,
    business_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    baseline_from: date | None = None,
    baseline_to: date | None = None,
    products_limit: int = Query(20, ge=1, le=100),
    products_offset: int = Query(0, ge=0),
    categories_limit: int = Query(20, ge=1, le=100),
    categories_offset: int = Query(0, ge=0),
) -> PeriodComparison:
    business = require_business(db, business_id)
    period = analytics.resolve_period(db, business, date_from, date_to)
    if date_from is None and date_to is None:
        period = Period(date_from=period.date_to - timedelta(days=29), date_to=period.date_to)
    baseline = comparison.baseline_period(business, db, period, baseline_from, baseline_to)
    return comparison.comparison(
        db,
        business,
        period,
        baseline,
        products_limit,
        products_offset,
        categories_limit,
        categories_offset,
    )


@router.get("/forecast", response_model=FinancialForecast, responses=ERRORS)
def financial_forecast(
    db: Database,
    business_id: UUID,
    period: SelectedPeriod,
    horizon_days: int = Query(30, ge=1, le=90),
    complete_calendar: bool = False,
    sales_change_percent: Decimal = Query(Decimal(0), ge=-50, le=100, decimal_places=2),
    expense_change_percent: Decimal = Query(Decimal(0), ge=-50, le=100, decimal_places=2),
) -> FinancialForecast:
    return forecast.forecast(
        db,
        business_id,
        period,
        horizon_days,
        complete_calendar,
        sales_change_percent,
        expense_change_percent,
    )
