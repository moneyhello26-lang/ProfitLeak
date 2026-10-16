from datetime import date, timedelta
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.analytics import Metric, Period
from app.schemas.planning import FinancialForecast, ForecastBacktest, ForecastPoint, ForecastTotals
from app.services import analytics
from app.services.comparison import NAMES, days
from app.services.import_parser import FileProblem

ZERO = Decimal("0.00")
MIN_DAYS = 28
WINDOW = 30


def calendar(period: Period) -> list[date]:
    return [period.date_from + timedelta(days=i) for i in range(days(period))]


def recent(period: Period) -> Period:
    # Subtract at most the available days, including near date.min.
    return Period(
        date_from=period.date_to - timedelta(days=min(WINDOW, days(period)) - 1),
        date_to=period.date_to,
    )


def derive(revenue: Metric, cogs: Metric, expenses: Metric) -> ForecastTotals:
    profit = (
        analytics.available(revenue.value - cogs.value)
        if (revenue.value is not None and cogs.value is not None)
        else revenue
        if revenue.value is None
        else cogs
    )
    operating = (
        analytics.available(profit.value - expenses.value)
        if (profit.value is not None and expenses.value is not None)
        else profit
        if profit.value is None
        else expenses
    )
    margin = (
        profit
        if profit.value is None
        else (
            analytics.available(profit.value / revenue.value * 100)
            if revenue.value
            else Metric(value=None, status="not_applicable", reason="zero_revenue")
        )
    )
    return ForecastTotals(
        revenue=revenue,
        cogs=cogs,
        gross_profit=profit,
        gross_margin_percent=margin,
        operating_expenses=expenses,
        operating_profit=operating,
    )


def fit(sales, expenses, period: Period, complete: bool):
    dates = calendar(period)
    observed_sales = [sales[d] for d in dates if d in sales]
    observed_expenses = [expenses[d] for d in dates if d in expenses]
    short = len(dates) < MIN_DAYS
    sales_reason = (
        "insufficient_history"
        if short
        else "no_sales"
        if not observed_sales
        else "incomplete_sales_calendar"
        if len(observed_sales) != len(dates) and not complete
        else None
    )
    cost_reason = sales_reason or (
        "missing_cost" if any(s.missing for s in observed_sales) else None
    )
    expense_reason = (
        "insufficient_history"
        if short
        else "no_expenses"
        if not observed_expenses
        else "incomplete_expense_calendar"
        if len(observed_expenses) != len(dates) and not complete
        else None
    )
    means = {}
    for weekday in range(7):
        weekday_dates = [d for d in dates if d.weekday() == weekday]
        means[weekday] = (
            analytics.unavailable(sales_reason)
            if sales_reason
            else analytics.available(
                sum((sales[d].revenue for d in weekday_dates if d in sales), ZERO)
                / len(weekday_dates)
            ),
            analytics.unavailable(cost_reason)
            if cost_reason
            else analytics.available(
                sum((sales[d].cost for d in weekday_dates if d in sales), ZERO) / len(weekday_dates)
            ),
        )
    # Spread the full 30-day expense ledger, including monthly rent, over the horizon.
    expense = (
        analytics.unavailable(expense_reason)
        if expense_reason
        else analytics.available(sum((e.amount for e in observed_expenses), ZERO) / len(dates))
    )
    return means, expense


def predict(
    means, expense: Metric, dates: list[date], sales_factor: Decimal, expense_factor: Decimal
):
    points = []
    for day in dates:
        revenue, cogs = means[day.weekday()]

        def scale(metric, factor):
            return (
                analytics.available(metric.value * factor) if metric.value is not None else metric
            )

        totals = derive(
            scale(revenue, sales_factor), scale(cogs, sales_factor), scale(expense, expense_factor)
        )
        points.append(ForecastPoint(date=day, **totals.model_dump()))
    return points


def total(points: list[ForecastPoint]) -> ForecastTotals:
    values = []
    for name in ("revenue", "cogs", "operating_expenses"):
        metrics = [getattr(point, name) for point in points]
        absent = next((metric for metric in metrics if metric.value is None), None)
        values.append(
            absent
            if absent is not None
            else analytics.available(sum((metric.value for metric in metrics), ZERO))
        )
    return derive(*values)


def backtest(sales, expenses, period: Period, complete: bool) -> ForecastBacktest:
    if days(period) < MIN_DAYS + 7:
        return ForecastBacktest(
            status="insufficient_data",
            reason="Нужно не менее 35 дней истории: 28 для расчёта и 7 для проверки.",
        )
    test_period = Period(date_from=period.date_to - timedelta(days=6), date_to=period.date_to)
    training_period = recent(
        Period(date_from=period.date_from, date_to=test_period.date_from - timedelta(days=1))
    )
    means, expense = fit(sales, expenses, training_period, complete)
    predicted = predict(means, expense, calendar(test_period), Decimal(1), Decimal(1))
    if any(p.revenue.value is None for p in predicted) or (
        not complete and any(d not in sales for d in calendar(test_period))
    ):
        return ForecastBacktest(
            status="insufficient_data",
            training_period=training_period,
            test_period=test_period,
            reason="Для проверки нужна полная история продаж в обучающем и проверочном окнах.",
        )
    errors, actual_sum = ZERO, ZERO
    for point in predicted:
        actual = sales[point.date].revenue if point.date in sales else ZERO
        errors += abs(actual - point.revenue.value)
        actual_sum += abs(actual)
    return ForecastBacktest(
        status="available",
        training_period=training_period,
        test_period=test_period,
        days=7,
        revenue_mae=analytics.rounded(errors / 7),
        revenue_wape_percent=analytics.rounded(errors / actual_sum * 100) if actual_sum else None,
    )


def forecast(
    db: Session,
    business_id: UUID,
    period: Period,
    horizon_days: int = 30,
    complete_calendar: bool = False,
    sales_change_percent: Decimal = ZERO,
    expense_change_percent: Decimal = ZERO,
) -> FinancialForecast:
    try:
        future = Period(
            date_from=period.date_to + timedelta(days=1),
            date_to=period.date_to + timedelta(days=horizon_days),
        )
    except OverflowError as error:
        raise FileProblem(
            "invalid_forecast", "Прогноз выходит за допустимый диапазон дат."
        ) from error
    training = recent(period)
    sales = analytics.sales_groups(db, business_id, period, "date")
    expenses = analytics.expense_groups(db, business_id, period, group_by="date")
    with localcontext() as context:
        context.prec = 64
        means, expense = fit(sales, expenses, training, complete_calendar)
        base = predict(means, expense, calendar(future), Decimal(1), Decimal(1))
        points = predict(
            means,
            expense,
            calendar(future),
            1 + sales_change_percent / 100,
            1 + expense_change_percent / 100,
        )
        totals = total(points)
        history = []
        for day in calendar(training):
            s, e = sales.get(day), expenses.get(day)
            revenue = (
                analytics.available(s.revenue)
                if s
                else analytics.available(ZERO)
                if (complete_calendar and sales)
                else analytics.unavailable("no_sales")
            )
            cost = (
                analytics.unavailable("missing_cost")
                if s and s.missing
                else (
                    analytics.available(s.cost)
                    if s
                    else analytics.available(ZERO)
                    if complete_calendar and sales
                    else analytics.unavailable("no_sales")
                )
            )
            exp = (
                analytics.available(e.amount)
                if e
                else analytics.available(ZERO)
                if (complete_calendar and expenses)
                else analytics.unavailable("no_expenses")
            )
            history.append(ForecastPoint(date=day, **derive(revenue, cost, exp).model_dump()))
        validation = backtest(sales, expenses, period, complete_calendar)
    ready = [
        getattr(totals, name).value is not None for name in NAMES if name != "gross_margin_percent"
    ]
    warnings = []
    if days(training) < MIN_DAYS:
        warnings.append("Загрузите минимум 28 календарных дней истории для прогноза.")
    if any(day not in sales for day in calendar(training)) and not complete_calendar:
        warnings.append(
            "В истории есть дни без продаж. Подтвердите полноту отчётов или загрузите данные."
        )
    if any(day not in expenses for day in calendar(training)) and not complete_calendar:
        warnings.append(
            "В истории есть дни без расходов: прогноз расходов и операционной прибыли недоступен."
        )
    if any(s.missing for d, s in sales.items() if training.date_from <= d <= training.date_to):
        warnings.append("Без себестоимости всех продаж нельзя прогнозировать прибыль.")
    if horizon_days > days(training):
        warnings.append(
            "Горизонт длиннее обучающего окна: результат особенно чувствителен "
            "к изменениям бизнеса."
        )
    if not any(d in sales or d in expenses for d in calendar(training)):
        warnings.append("Подходящих данных для прогноза нет. Начните с импорта продаж и расходов.")
    return FinancialForecast(
        business_id=business_id,
        period=period,
        training_period=training,
        forecast_period=future,
        horizon_days=horizon_days,
        training_days=days(training),
        observed_sales_days=sum(d in sales for d in calendar(training)),
        observed_expense_days=sum(d in expenses for d in calendar(training)),
        complete_calendar=complete_calendar,
        sales_change_percent=sales_change_percent,
        expense_change_percent=expense_change_percent,
        status="available" if all(ready) else "partial" if any(ready) else "insufficient_data",
        history=history,
        points=points,
        totals=totals,
        baseline_totals=total(base),
        backtest=validation,
        assumptions=[
            "Выручка и себестоимость: среднее для соответствующего дня недели "
            "за последние 30 дней выбранной истории (минимум 28).",
            "Расходы: среднее за все календарные дни того же окна; "
            "аренда и разовые платежи распределяются равномерно.",
            "Сценарий продаж одинаково изменяет выручку и себестоимость; "
            "сценарий расходов изменяет только операционные расходы.",
            "Цены, товарный состав и режим работы считаются стабильными. "
            "Тренд, праздники и годовая сезонность не моделируются.",
            "Прогноз — расчётный сценарий, а не гарантия. Проверка на одной неделе "
            "не определяет точность всего будущего горизонта.",
            "Дни без записей считаются нулевыми только при явном подтверждении полноты отчётов. "
            "Полностью отсутствующий тип данных остаётся недоступным.",
        ],
        warnings=warnings,
    )
