from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import Database, require_business
from app.schemas.analytics import (
    DashboardSummary,
    DemoLoad,
    ExpensesAnalytics,
    Period,
    ProductsAnalytics,
    RevenueAnalytics,
)
from app.schemas.imports import ErrorResponse
from app.services import analytics
from app.services.demo import load_demo

router = APIRouter(prefix="/api/v1", tags=["Analytics"])
ERRORS = {status: {"model": ErrorResponse} for status in (400, 404)}


def query_period(
    db: Database, business_id: UUID, date_from: date | None = None, date_to: date | None = None
) -> Period:
    business = require_business(db, business_id)
    return analytics.resolve_period(db, business, date_from, date_to)


SelectedPeriod = Annotated[Period, Depends(query_period)]


@router.post("/demo/load", response_model=DemoLoad)
def demo(db: Database):
    loaded = load_demo(db)
    db.commit()
    return loaded


@router.get("/dashboard/summary", response_model=DashboardSummary, responses=ERRORS)
def dashboard(db: Database, business_id: UUID, period: SelectedPeriod):
    return analytics.summary(db, business_id, period)


@router.get("/analytics/revenue", response_model=RevenueAnalytics, responses=ERRORS)
def revenue(db: Database, business_id: UUID, period: SelectedPeriod):
    return analytics.revenue_series(db, business_id, period)


@router.get("/analytics/expenses", response_model=ExpensesAnalytics, responses=ERRORS)
def expenses(db: Database, business_id: UUID, period: SelectedPeriod):
    return analytics.expense_categories(db, business_id, period)


@router.get("/analytics/products", response_model=ProductsAnalytics, responses=ERRORS)
def products(
    db: Database,
    business_id: UUID,
    period: SelectedPeriod,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return analytics.product_profitability(db, business_id, period, limit, offset)
