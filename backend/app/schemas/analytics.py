from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.imports import BusinessRead


class Period(BaseModel):
    date_from: date
    date_to: date


class Metric(BaseModel):
    value: Decimal | None
    status: Literal["available", "insufficient_data", "not_applicable"]
    reason: (
        Literal[
            "no_sales",
            "missing_cost",
            "no_expenses",
            "zero_revenue",
            "insufficient_history",
            "incomplete_sales_calendar",
            "incomplete_expense_calendar",
        ]
        | None
    ) = None


class DashboardSummary(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    period: Period
    sales_rows: int
    expense_rows: int
    missing_cost_rows: int
    revenue: Metric
    cogs: Metric
    gross_profit: Metric
    gross_margin_percent: Metric
    operating_expenses: Metric
    operating_profit: Metric


class RevenuePoint(BaseModel):
    date: date
    sales_rows: int
    revenue: Metric


class RevenueAnalytics(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    period: Period
    points: list[RevenuePoint]


class ExpenseCategory(BaseModel):
    category: str
    amount: Decimal
    expense_rows: int


class ExpensesAnalytics(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    period: Period
    total: Metric
    categories: list[ExpenseCategory]


class ProductProfitability(BaseModel):
    product_id: UUID
    external_id: str
    name: str
    sales_rows: int
    missing_cost_rows: int
    net_quantity: Decimal
    revenue: Metric
    cogs: Metric
    gross_profit: Metric
    gross_margin_percent: Metric


class ProductsAnalytics(BaseModel):
    business_id: UUID
    currency: Literal["KZT"] = "KZT"
    period: Period
    items: list[ProductProfitability]
    total: int
    limit: int
    offset: int


class DemoLoad(BaseModel):
    business: BusinessRead
    dataset_version: str
    period: Period
    sales_rows: int
    expense_rows: int
    product_count: int
    already_loaded: bool
