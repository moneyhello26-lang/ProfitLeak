"""Explainable rules on confirmed records; no LLM or floating point arithmetic."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import UUID

from app.schemas.analytics import Period
from app.schemas.insights import InsightEvidence, InsightType, RuleCheck, SourceRow
from app.services.analytics import ZERO, rounded

RULES_VERSION = "rules-v1"
MIN_WINDOW_DAYS = 7
EXPENSE_THRESHOLD = Decimal("25.00")
MARGIN_THRESHOLD = Decimal("10.00")
LOW_MARGIN_THRESHOLD = Decimal("20.00")
SALES_THRESHOLD = Decimal("20.00")


@dataclass(frozen=True)
class SaleRecord:
    source: SourceRow
    product_id: UUID
    name: str
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal | None


@dataclass(frozen=True)
class ExpenseRecord:
    source: SourceRow
    category: str
    description: str


@dataclass
class Signal:
    type: InsightType
    key: str
    severity: str
    confidence: str
    evidence: InsightEvidence
    recommendation: str
    savings: Decimal | None = None


@dataclass
class Detection:
    current: Period | None
    baseline: Period | None
    signals: list[Signal]
    checks: list[RuleCheck]


def comparison_periods(period: Period) -> tuple[Period | None, Period | None]:
    # Equal adjacent windows entirely within the requested dates. Default 90d -> 30d/30d.
    days = min(30, ((period.date_to - period.date_from).days + 1) // 2)
    if days < MIN_WINDOW_DAYS:
        return None, None
    current = Period(date_from=period.date_to - timedelta(days=days - 1), date_to=period.date_to)
    baseline = Period(
        date_from=current.date_from - timedelta(days=days),
        date_to=current.date_from - timedelta(days=1),
    )
    return current, baseline


def in_period(record, period: Period) -> bool:
    return period.date_from <= record.source.date <= period.date_to


def observed_days(records) -> int:
    return len({record.source.date for record in records})


def expense_amount(records) -> Decimal:
    return sum(
        ((-1 if r.source.record_type == "refund" else 1) * r.source.amount for r in records), ZERO
    )


def sales_totals(records) -> tuple[Decimal, Decimal | None, Decimal]:
    revenue, cost, quantity = ZERO, ZERO, Decimal("0.000")
    missing = False
    for row in records:
        sign = -1 if row.source.record_type == "return" else 1
        revenue += sign * rounded(row.quantity * row.unit_price)
        quantity += sign * row.quantity
        if row.unit_cost is None:
            missing = True
        else:
            cost += sign * rounded(row.quantity * row.unit_cost)
    return revenue, None if missing else cost, quantity


def evidence(
    *,
    title,
    explanation,
    entity,
    current,
    baseline,
    value,
    base_value,
    formula,
    current_rows,
    baseline_rows=(),
    **extra,
) -> InsightEvidence:
    def latest(records, count):
        return sorted(
            (r.source for r in records),
            key=lambda r: (r.date, r.filename, r.source_row, str(r.record_id)),
            reverse=True,
        )[:count]

    sources = latest(current_rows, 10 if baseline_rows else 20) + latest(baseline_rows, 10)
    return InsightEvidence(
        title=title,
        explanation=explanation,
        entity=entity,
        current_period=current,
        baseline_period=baseline,
        current_value=rounded(value),
        baseline_value=rounded(base_value) if base_value is not None else None,
        formula=formula,
        current_rows=len(current_rows),
        baseline_rows=len(baseline_rows),
        current_days=observed_days(current_rows),
        baseline_days=observed_days(baseline_rows),
        source_rows=sources,
        source_rows_total=len(current_rows) + len(baseline_rows),
        caveat="Расчёт относится к загруженным операциям. Полнота учёта не подтверждена.",
        **extra,
    )


def detect(period: Period, sales: list[SaleRecord], expenses: list[ExpenseRecord]) -> Detection:
    # Callers cannot accidentally include records outside the selected period.
    sales = [r for r in sales if in_period(r, period)]
    expenses = [r for r in expenses if in_period(r, period)]
    with localcontext() as context:
        context.prec = 64
        return _detect(period, sales, expenses)


def _detect(period, sales, expenses) -> Detection:
    current, baseline = comparison_periods(period)
    signals = []
    checks = []

    def check(kind, evaluated, skipped, reason):
        checks.append(
            RuleCheck(
                type=kind,
                status="evaluated" if evaluated else "insufficient_data",
                signals=sum(s.type == kind for s in signals),
                skipped_entities=skipped,
                reason=reason,
            )
        )

    categories = defaultdict(list)
    products = defaultdict(list)
    for row in expenses:
        categories[row.category].append(row)
    for row in sales:
        products[row.product_id].append(row)

    evaluated, skipped = 0, 0
    for category, rows in sorted(categories.items()):
        a = [r for r in rows if current and in_period(r, current)]
        b = [r for r in rows if baseline and in_period(r, baseline)]
        amount, base = expense_amount(a), expense_amount(b)
        if observed_days(a) < 7 or observed_days(b) < 7 or base <= 0:
            skipped += 1
            continue
        evaluated += 1
        deviation = (amount - base) / base * 100
        if deviation < EXPENSE_THRESHOLD:
            continue
        signals.append(
            Signal(
                type="EXPENSE_SPIKE",
                key=category,
                severity="high" if deviation >= 50 else "medium",
                confidence="medium",
                evidence=evidence(
                    title=f"Рост расходов: {category}",
                    explanation="Расходы категории выросли относительно соседнего периода "
                    "той же длины.",
                    entity=category,
                    current=current,
                    baseline=baseline,
                    value=amount,
                    base_value=base,
                    formula="(расходы текущего периода − расходы базового) "
                    "/ расходы базового × 100",
                    current_rows=a,
                    baseline_rows=b,
                    deviation_percent=rounded(deviation),
                    threshold=EXPENSE_THRESHOLD,
                    category=category,
                    savings_assumption="Возврат к расходам базового периода "
                    "при том же объёме закупок. "
                    "Объём закупок в файле не указан; оценка требует проверки.",
                ),
                recommendation="Сравните объём закупок, цены поставщика и первичные документы. "
                "Проверьте повторные платежи, затем обсудите цену или объём заказа.",
                savings=rounded(amount - base),
            )
        )
    check(
        "EXPENSE_SPIKE",
        evaluated,
        skipped,
        "Порог роста 25%; минимум 7 дней с расходами категории в каждом окне и положительная база.",
    )

    evaluated, skipped = 0, 0
    for product_id, rows in sorted(products.items(), key=lambda item: str(item[0])):
        a = [r for r in rows if current and in_period(r, current)]
        b = [r for r in rows if baseline and in_period(r, baseline)]
        rev, cost, qty = sales_totals(a)
        base_rev, base_cost, base_qty = sales_totals(b)
        if (
            observed_days(a) < 7
            or observed_days(b) < 7
            or cost is None
            or base_cost is None
            or rev <= 0
            or base_rev <= 0
            or qty < 10
            or base_qty < 10
        ):
            skipped += 1
            continue
        evaluated += 1
        margin = (rev - cost) / rev * 100
        base_margin = (base_rev - base_cost) / base_rev * 100
        drop = base_margin - margin
        if drop < MARGIN_THRESHOLD:
            continue
        signals.append(
            Signal(
                type="MARGIN_DROP",
                key=str(product_id),
                severity="high" if drop >= 20 else "medium",
                confidence="medium",
                evidence=evidence(
                    title=f"Падение маржи: {rows[0].name}",
                    explanation="Доля валовой прибыли товара снизилась. Проверьте изменение цены "
                    "и себестоимости по исходным продажам.",
                    entity=rows[0].name,
                    current=current,
                    baseline=baseline,
                    value=margin,
                    base_value=base_margin,
                    value_unit="percent",
                    deviation_pp=rounded(-drop),
                    threshold=MARGIN_THRESHOLD,
                    product_id=product_id,
                    formula="(выручка − себестоимость) / выручка × 100; "
                    "падение = базовая маржа − текущая маржа в процентных пунктах",
                    current_rows=a,
                    baseline_rows=b,
                    current_revenue=rev,
                    current_cogs=cost,
                    baseline_revenue=base_rev,
                    baseline_cogs=base_cost,
                    savings_assumption="Восстановление базовой маржи при текущей выручке: "
                    "выручка × (базовая маржа − текущая маржа) / 100. "
                    "Оценка до операционных расходов, без прогноза спроса.",
                ),
                recommendation="Сверьте закупочную цену и рецептуру, скидки и цену продажи. "
                "Рассмотрите другого поставщика или изменение цены и проверьте влияние на спрос.",
                savings=rounded(rev * drop / 100),
            )
        )
    check(
        "MARGIN_DROP",
        evaluated,
        skipped,
        "Порог падения 10 п.п.; минимум 7 дней и 10 единиц в каждом окне. "
        "Нужна полная себестоимость.",
    )

    evaluated, skipped = 0, 0
    for product_id, rows in sorted(products.items(), key=lambda item: str(item[0])):
        rev, cost, qty = sales_totals(rows)
        if len(rows) < 5 or observed_days(rows) < 3 or qty < 10 or cost is None or rev <= 0:
            skipped += 1
            continue
        evaluated += 1
        margin = (rev - cost) / rev * 100
        if margin > LOW_MARGIN_THRESHOLD:
            continue
        signals.append(
            Signal(
                type="LOW_PROFIT_PRODUCT",
                key=str(product_id),
                severity="high" if margin < 0 else "medium",
                confidence="medium",
                evidence=evidence(
                    title=f"Низкая маржа: {rows[0].name}",
                    explanation="Маржа товара не превышает 20% до операционных расходов. "
                    "Это порог правила, а не норматив вашей отрасли.",
                    entity=rows[0].name,
                    current=period,
                    baseline=None,
                    value=margin,
                    base_value=None,
                    value_unit="percent",
                    threshold=LOW_MARGIN_THRESHOLD,
                    product_id=product_id,
                    formula="(выручка − себестоимость) / выручка × 100",
                    current_rows=rows,
                    current_revenue=rev,
                    current_cogs=cost,
                ),
                recommendation="Проверьте цену, закупочную стоимость и скидки. "
                "Учитывайте роль товара в ассортименте перед изменением цены "
                "или снятием с продажи.",
            )
        )
    check(
        "LOW_PROFIT_PRODUCT",
        evaluated,
        skipped,
        "Маржа ≤20%; минимум 5 строк, 3 дня и 10 единиц. Нужна полная себестоимость.",
    )

    a = [r for r in sales if current and in_period(r, current)]
    b = [r for r in sales if baseline and in_period(r, baseline)]
    rev, _, _ = sales_totals(a)
    base_rev, _, _ = sales_totals(b)
    window_days = (current.date_to - current.date_from).days + 1 if current else 0
    valid = (
        window_days >= 7
        and observed_days(a) == window_days
        and observed_days(b) == window_days
        and base_rev > 0
        and rev >= 0
    )
    if valid and (base_rev - rev) / base_rev * 100 >= SALES_THRESHOLD:
        signals.append(
            Signal(
                type="SALES_DROP",
                key="business",
                severity="medium",
                confidence="medium",
                evidence=evidence(
                    title="Снижение выручки",
                    entity="Все товары",
                    explanation="Выручка снизилась относительно соседнего периода той же длины. "
                    "Это отклонение продаж, а не доказанный убыток.",
                    current=current,
                    baseline=baseline,
                    value=rev,
                    base_value=base_rev,
                    deviation_percent=rounded((rev - base_rev) / base_rev * 100),
                    threshold=SALES_THRESHOLD,
                    formula="(текущая выручка − базовая выручка) / базовая выручка × 100",
                    current_rows=a,
                    baseline_rows=b,
                ),
                recommendation="Сверьте полноту загрузки, часы работы и сезонность. "
                "Сравните количество продаж и цены, затем проверьте ассортимент и продвижение.",
            )
        )
    check(
        "SALES_DROP",
        int(valid),
        int(not valid),
        "Порог снижения 20%; записи продаж нужны за каждый день обоих окон, база должна быть >0.",
    )

    duplicates = defaultdict(list)
    eligible = 0
    for row in expenses:
        description = " ".join(row.description.split()).casefold()
        if row.source.record_type != "expense" or not description or row.source.amount <= 0:
            continue
        eligible += 1
        key = (row.source.date, row.category, description, row.source.amount)
        duplicates[key].append(row)
    for key, rows in sorted(duplicates.items()):
        if len(rows) < 2:
            continue
        day, category, _, amount = key
        proof = evidence(
            title=f"Возможный повторный платёж: {category}",
            explanation="Совпали дата, категория, описание и сумма. Реквизитов платежа "
            "в формате импорта нет, поэтому это кандидат на проверку человеком.",
            entity=category,
            current=Period(date_from=day, date_to=day),
            baseline=None,
            value=amount,
            base_value=None,
            formula="совпадение даты, категории, нормализованного описания и суммы расхода",
            current_rows=rows,
            category=category,
        )
        proof.caveat = "Одинаковые расходы могут быть отдельными законными платежами. "
        proof.caveat += "Сверьте платёжные документы; записи не удаляются автоматически."
        signals.append(
            Signal(
                type="POSSIBLE_DUPLICATE",
                key="|".join(map(str, key)),
                severity="medium",
                confidence="low",
                evidence=proof,
                recommendation="Сравните чеки, счета и банковские реквизиты обеих записей. "
                "Если подтвердится один платёж, исправьте учёт; если два — оставьте обе записи.",
            )
        )
    check(
        "POSSIBLE_DUPLICATE",
        int(eligible >= 2),
        len(expenses) - eligible,
        "Совпадают дата, категория, непустое описание и положительная сумма. Возвраты исключены.",
    )
    return Detection(current=current, baseline=baseline, signals=signals, checks=checks)
