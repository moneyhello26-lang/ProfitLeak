from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Business, Expense, ImportBatch, Product, Sale
from app.schemas.analytics import (
    DashboardSummary,
    ExpenseCategory,
    ExpensesAnalytics,
    Metric,
    Period,
    ProductProfitability,
    ProductsAnalytics,
    RevenueAnalytics,
    RevenuePoint,
)
from app.services.import_parser import FileProblem

ZERO = Decimal("0.00")
CENT = Decimal("0.01")


@dataclass
class SalesTotals:
    rows: int = 0
    missing: int = 0
    revenue: Decimal = ZERO
    cost: Decimal = ZERO
    quantity: Decimal = Decimal("0.000")


@dataclass
class ExpenseTotals:
    rows: int = 0
    amount: Decimal = ZERO


def confirmed(model):
    return (
        select(ImportBatch.id)
        .where(ImportBatch.id == model.import_id, ImportBatch.status == "confirmed")
        .correlate(model)
        .exists()
    )


def resolve_period(
    db: Session, business: Business, date_from: date | None, date_to: date | None
) -> Period:
    try:
        if date_from is not None and date_to is None:
            date_to = date_from + timedelta(days=89)
        if date_to is None:
            latest_sale = db.scalar(
                select(func.max(Sale.date)).where(Sale.business_id == business.id, confirmed(Sale))
            )
            latest_expense = db.scalar(
                select(func.max(Expense.date)).where(
                    Expense.business_id == business.id, confirmed(Expense)
                )
            )
            available = [day for day in (latest_sale, latest_expense) if day is not None]
            date_to = (
                max(available) if available else datetime.now(ZoneInfo(business.timezone)).date()
            )
        if date_from is None:
            date_from = date_to - timedelta(days=89)
    except OverflowError as error:
        raise FileProblem("invalid_period", "Период выходит за допустимые границы дат.") from error
    if date_from > date_to or (date_to - date_from).days >= 366:
        raise FileProblem("invalid_period", "Выберите период от 1 до 366 дней.")
    return Period(date_from=date_from, date_to=date_to)


def bounds(model, business_id: UUID, period: Period):
    return (
        model.business_id == business_id,
        model.date >= period.date_from,
        model.date <= period.date_to,
        confirmed(model),
    )


def rounded(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 64
        return value.quantize(CENT, rounding=ROUND_HALF_UP)


def available(value: Decimal) -> Metric:
    return Metric(value=rounded(value), status="available")


def unavailable(reason: str) -> Metric:
    return Metric(value=None, status="insufficient_data", reason=reason)


def sale_metrics(revenue: Decimal | None, cost: Decimal | None, rows: int, missing: int):
    if not rows:
        absent = unavailable("no_sales")
        return absent, absent, absent, absent
    revenue = revenue if revenue is not None else ZERO
    revenue_metric = available(revenue)
    if missing:
        absent = unavailable("missing_cost")
        return revenue_metric, absent, absent, absent
    with localcontext() as context:
        context.prec = 64
        cost = cost if cost is not None else ZERO
        profit = revenue - cost
        margin = (
            available(profit / revenue * 100)
            if revenue != 0
            else Metric(value=None, status="not_applicable", reason="zero_revenue")
        )
        return revenue_metric, available(cost), available(profit), margin


def sales_groups(db: Session, business_id: UUID, period: Period, group_by: str | None = None):
    statement = (
        select(
            Sale.date,
            Sale.product_id,
            Sale.record_type,
            Sale.quantity,
            Sale.unit_price,
            Sale.unit_cost,
        )
        .where(*bounds(Sale, business_id, period))
        .execution_options(yield_per=1000)
    )
    groups = {}
    # Storage converts fixed point values to Decimal; financial arithmetic stays in Python.
    with localcontext() as context, db.execute(statement) as records:
        context.prec = 64
        for record in records:
            key = getattr(record, group_by) if group_by else None
            totals = groups.setdefault(key, SalesTotals())
            sign = -1 if record.record_type == "return" else 1
            totals.rows += 1
            totals.quantity += sign * record.quantity
            totals.revenue += sign * rounded(record.quantity * record.unit_price)
            if record.unit_cost is None:
                totals.missing += 1
            else:
                totals.cost += sign * rounded(record.quantity * record.unit_cost)
    return groups


def expense_groups(
    db: Session,
    business_id: UUID,
    period: Period,
    by_category: bool = False,
    group_by: str | None = None,
):
    statement = (
        select(Expense.date, Expense.category, Expense.record_type, Expense.amount)
        .where(*bounds(Expense, business_id, period))
        .execution_options(yield_per=1000)
    )
    groups = {}
    with localcontext() as context, db.execute(statement) as records:
        context.prec = 64
        for record in records:
            key = (
                record.category if by_category else getattr(record, group_by) if group_by else None
            )
            totals = groups.setdefault(key, ExpenseTotals())
            totals.rows += 1
            totals.amount += (-1 if record.record_type == "refund" else 1) * record.amount
    return groups


def summary(db: Session, business_id: UUID, period: Period) -> DashboardSummary:
    sales = sales_groups(db, business_id, period).get(None, SalesTotals())
    expenses = expense_groups(db, business_id, period).get(None, ExpenseTotals())
    revenue, cogs, profit, margin = sale_metrics(
        sales.revenue, sales.cost, sales.rows, sales.missing
    )
    expenses_metric = available(expenses.amount) if expenses.rows else unavailable("no_expenses")
    if profit.value is None:
        operating_profit = profit
    elif expenses_metric.value is None:
        operating_profit = expenses_metric
    else:
        with localcontext() as context:
            context.prec = 64
            operating_profit = available(profit.value - expenses_metric.value)
    return DashboardSummary(
        business_id=business_id,
        period=period,
        sales_rows=sales.rows,
        expense_rows=expenses.rows,
        missing_cost_rows=sales.missing,
        revenue=revenue,
        cogs=cogs,
        gross_profit=profit,
        gross_margin_percent=margin,
        operating_expenses=expenses_metric,
        operating_profit=operating_profit,
    )


def revenue_series(db: Session, business_id: UUID, period: Period) -> RevenueAnalytics:
    observed = sales_groups(db, business_id, period, "date")
    points = []
    for offset in range((period.date_to - period.date_from).days + 1):
        day = period.date_from + timedelta(days=offset)
        row = observed.get(day)
        points.append(
            RevenuePoint(
                date=day,
                sales_rows=row.rows if row else 0,
                revenue=available(row.revenue) if row else unavailable("no_sales"),
            )
        )
    return RevenueAnalytics(business_id=business_id, period=period, points=points)


def expense_categories(db: Session, business_id: UUID, period: Period) -> ExpensesAnalytics:
    groups = expense_groups(db, business_id, period, by_category=True)
    categories = [
        ExpenseCategory(category=category, amount=rounded(totals.amount), expense_rows=totals.rows)
        for category, totals in sorted(
            groups.items(), key=lambda item: (item[1].amount.copy_negate(), item[0])
        )
    ]
    with localcontext() as context:
        context.prec = 64
        total = (
            available(sum((item.amount for item in categories), ZERO))
            if categories
            else unavailable("no_expenses")
        )
    return ExpensesAnalytics(
        business_id=business_id, period=period, total=total, categories=categories
    )


def product_profitability(
    db: Session, business_id: UUID, period: Period, limit: int, offset: int
) -> ProductsAnalytics:
    groups = sales_groups(db, business_id, period, "product_id")
    items = []
    products = (
        db.scalars(
            select(Product).where(Product.business_id == business_id, Product.id.in_(list(groups)))
        )
        if groups
        else []
    )
    for product in products:
        row = groups[product.id]
        rev, cogs, gross, margin = sale_metrics(row.revenue, row.cost, row.rows, row.missing)
        items.append(
            ProductProfitability(
                product_id=product.id,
                external_id=product.external_id,
                name=product.name,
                sales_rows=row.rows,
                missing_cost_rows=row.missing,
                net_quantity=row.quantity,
                revenue=rev,
                cogs=cogs,
                gross_profit=gross,
                gross_margin_percent=margin,
            )
        )
    items.sort(
        key=lambda item: (
            item.gross_profit.value is None,
            item.gross_profit.value.copy_negate() if item.gross_profit.value is not None else ZERO,
            item.external_id,
        )
    )
    return ProductsAnalytics(
        business_id=business_id,
        period=period,
        items=items[offset : offset + limit],
        total=len(items),
        limit=limit,
        offset=offset,
    )
