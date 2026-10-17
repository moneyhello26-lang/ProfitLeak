from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext

from sqlalchemy.orm import Session

from app.schemas.analytics import Metric, Period
from app.schemas.planning import (
    CategoryComparison,
    ComparisonPoint,
    MetricComparison,
    NamedComparison,
    PeriodComparison,
    ProductComparison,
)
from app.services import analytics
from app.services.import_parser import FileProblem

NAMES = (
    "revenue",
    "cogs",
    "gross_profit",
    "gross_margin_percent",
    "operating_expenses",
    "operating_profit",
)


def days(period: Period) -> int:
    return (period.date_to - period.date_from).days + 1


def baseline_period(business, db, current: Period, start: date | None, end: date | None):
    if (start is None) != (end is None):
        raise FileProblem("invalid_baseline", "Укажите обе даты базового периода.")
    if start is None:
        try:
            end = current.date_from - timedelta(days=1)
            start = end - timedelta(days=days(current) - 1)
        except OverflowError as error:
            raise FileProblem(
                "invalid_baseline", "Базовый период выходит за диапазон дат."
            ) from error
    baseline = analytics.resolve_period(db, business, start, end)
    if baseline.date_to >= current.date_from:
        raise FileProblem(
            "overlapping_periods", "Базовый период должен завершаться до выбранного периода."
        )
    return baseline


def growth(current: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline == 0:
        return Decimal("0.00") if current == 0 else None
    return analytics.rounded((current - baseline) / abs(baseline) * 100)


def compare(
    current: Metric, baseline: Metric, current_days: int, baseline_days: int, unit="money"
) -> MetricComparison:
    with localcontext() as context:
        context.prec = 64
        c, b = current.value, baseline.value
        comparable = c is not None and b is not None
        # Compute differences before rounding the daily means.
        cd = c / current_days if c is not None and unit != "percent" else None
        bd = b / baseline_days if b is not None and unit != "percent" else None

        def rounded(value):
            return (
                value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if (unit == "quantity")
                else analytics.rounded(value)
            )

        return MetricComparison(
            current=current,
            baseline=baseline,
            unit=unit,
            change=rounded(c - b) if comparable else None,
            change_percent=growth(c, b) if comparable and unit != "percent" else None,
            current_per_day=rounded(cd) if cd is not None else None,
            baseline_per_day=rounded(bd) if bd is not None else None,
            per_day_change=rounded(cd - bd) if cd is not None and bd is not None else None,
            per_day_change_percent=growth(cd, bd) if cd is not None and bd is not None else None,
        )


def presence(current, baseline):
    return "both" if current and baseline else "current_only" if current else "baseline_only"


def comparison(
    db: Session,
    business,
    current: Period,
    baseline: Period,
    products_limit=20,
    products_offset=0,
    categories_limit=20,
    categories_offset=0,
) -> PeriodComparison:
    current_days, baseline_days = days(current), days(baseline)
    current_summary = analytics.summary(db, business.id, current)
    baseline_summary = analytics.summary(db, business.id, baseline)
    metrics = [
        NamedComparison(
            name=name,
            **compare(
                getattr(current_summary, name),
                getattr(baseline_summary, name),
                current_days,
                baseline_days,
                "percent" if name == "gross_margin_percent" else "money",
            ).model_dump(),
        )
        for name in NAMES
    ]
    # The service limit applies after aggregation, independently of the public product endpoint.
    cp = {
        p.product_id: p
        for p in analytics.product_profitability(
            db, business.id, current, limit=2**63 - 1, offset=0
        ).items
    }
    bp = {
        p.product_id: p
        for p in analytics.product_profitability(
            db, business.id, baseline, limit=2**63 - 1, offset=0
        ).items
    }
    products = []
    for product_id in cp.keys() | bp.keys():
        c, b = cp.get(product_id), bp.get(product_id)
        product = c or b
        values = {}
        for name in ("revenue", "gross_profit", "gross_margin_percent", "quantity"):

            def value(row):
                if row is None:
                    return analytics.unavailable("no_sales")
                if name == "quantity":
                    return Metric(value=row.net_quantity, status="available")
                return getattr(row, name)

            values[name] = compare(
                value(c),
                value(b),
                current_days,
                baseline_days,
                "percent"
                if name == "gross_margin_percent"
                else "quantity"
                if name == "quantity"
                else "money",
            )
        products.append(
            ProductComparison(
                product_id=product_id,
                external_id=product.external_id,
                name=product.name,
                presence=presence(c, b),
                **values,
            )
        )
    # Largest recorded revenue movements first; one-period products are still included.
    products.sort(
        key=lambda p: (
            (
                p.revenue.change
                if p.revenue.change is not None
                else p.revenue.current.value or p.revenue.baseline.value or Decimal(0)
            )
            .copy_abs()
            .copy_negate(),
            p.external_id,
        )
    )
    cc = analytics.expense_groups(db, business.id, current, by_category=True)
    bc = analytics.expense_groups(db, business.id, baseline, by_category=True)
    categories = []
    for category in cc.keys() | bc.keys():
        c, b = cc.get(category), bc.get(category)
        categories.append(
            CategoryComparison(
                category=category,
                presence=presence(c, b),
                amount=compare(
                    analytics.available(c.amount) if c else analytics.unavailable("no_expenses"),
                    analytics.available(b.amount) if b else analytics.unavailable("no_expenses"),
                    current_days,
                    baseline_days,
                ),
            )
        )
    categories.sort(
        key=lambda c: (
            (
                c.amount.change
                if c.amount.change is not None
                else c.amount.current.value or c.amount.baseline.value or Decimal(0)
            )
            .copy_abs()
            .copy_negate(),
            c.category,
        )
    )
    cs = analytics.sales_groups(db, business.id, current, "date")
    bs = analytics.sales_groups(db, business.id, baseline, "date")
    points = []
    for i in range(max(current_days, baseline_days)):
        cdate = current.date_from + timedelta(days=i) if i < current_days else None
        bdate = baseline.date_from + timedelta(days=i) if i < baseline_days else None
        c, b = cs.get(cdate), bs.get(bdate)
        points.append(
            ComparisonPoint(
                day=i + 1,
                current_date=cdate,
                baseline_date=bdate,
                current=analytics.available(c.revenue) if c else analytics.unavailable("no_sales"),
                baseline=analytics.available(b.revenue) if b else analytics.unavailable("no_sales"),
            )
        )
    warnings = []
    if current_days != baseline_days:
        warnings.append(
            "Периоды разной длины. Для сопоставления темпа используйте среднее за день."
        )
    if len(cs) < current_days or len(bs) < baseline_days:
        warnings.append(
            "Есть дни без записей о продажах. Отсутствующие данные не заменяются нулями."
        )
    if current_summary.missing_cost_rows or baseline_summary.missing_cost_rows:
        warnings.append("Есть продажи без себестоимости: часть показателей прибыли недоступна.")
    return PeriodComparison(
        business_id=business.id,
        current=current_summary,
        baseline=baseline_summary,
        current_days=current_days,
        baseline_days=baseline_days,
        current_sales_days=len(cs),
        baseline_sales_days=len(bs),
        metrics=metrics,
        points=points,
        products=products[products_offset : products_offset + products_limit],
        products_total=len(products),
        products_limit=products_limit,
        products_offset=products_offset,
        categories=categories[categories_offset : categories_offset + categories_limit],
        categories_total=len(categories),
        categories_limit=categories_limit,
        categories_offset=categories_offset,
        warnings=warnings,
    )
