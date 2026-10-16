from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.analytics import DashboardSummary, Metric, Period

MetricName = Literal[
    "revenue",
    "cogs",
    "gross_profit",
    "gross_margin_percent",
    "operating_expenses",
    "operating_profit",
]


class MetricComparison(BaseModel):
    current: Metric
    baseline: Metric
    change: Decimal | None
    change_percent: Decimal | None
    current_per_day: Decimal | None
    baseline_per_day: Decimal | None
    per_day_change: Decimal | None
    per_day_change_percent: Decimal | None
    unit: Literal["money", "percent", "quantity"] = "money"


class NamedComparison(MetricComparison):
    name: MetricName


class ProductComparison(BaseModel):
    product_id: UUID
    external_id: str
    name: str
    presence: Literal["both", "current_only", "baseline_only"]
    revenue: MetricComparison
    gross_profit: MetricComparison
    gross_margin_percent: MetricComparison
    quantity: MetricComparison


class CategoryComparison(BaseModel):
    category: str
    presence: Literal["both", "current_only", "baseline_only"]
    amount: MetricComparison


class ComparisonPoint(BaseModel):
    day: int
    current_date: date | None
    baseline_date: date | None
    current: Metric
    baseline: Metric


class PeriodComparison(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    current: DashboardSummary
    baseline: DashboardSummary
    current_days: int
    baseline_days: int
    current_sales_days: int
    baseline_sales_days: int
    metrics: list[NamedComparison]
    points: list[ComparisonPoint]
    products: list[ProductComparison]
    products_total: int
    products_offset: int
    products_limit: int
    categories: list[CategoryComparison]
    categories_total: int
    categories_offset: int
    categories_limit: int
    warnings: list[str]


class ForecastTotals(BaseModel):
    revenue: Metric
    cogs: Metric
    gross_profit: Metric
    gross_margin_percent: Metric
    operating_expenses: Metric
    operating_profit: Metric


class ForecastPoint(ForecastTotals):
    date: date


class ForecastBacktest(BaseModel):
    status: Literal["available", "insufficient_data"]
    reason: str | None = None
    training_period: Period | None = None
    test_period: Period | None = None
    days: int = 0
    revenue_mae: Decimal | None = None
    revenue_wape_percent: Decimal | None = None


class FinancialForecast(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    period: Period
    training_period: Period
    forecast_period: Period
    horizon_days: int
    training_days: int
    observed_sales_days: int
    observed_expense_days: int
    complete_calendar: bool
    sales_change_percent: Decimal
    expense_change_percent: Decimal
    status: Literal["available", "partial", "insufficient_data"]
    method: Literal["weekday_mean_30d"] = "weekday_mean_30d"
    history: list[ForecastPoint]
    points: list[ForecastPoint]
    totals: ForecastTotals
    baseline_totals: ForecastTotals
    backtest: ForecastBacktest
    assumptions: list[str]
    warnings: list[str]
