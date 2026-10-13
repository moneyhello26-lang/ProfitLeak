import csv
import io
import json
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from app.schemas.analytics import Period
from app.schemas.insights import SourceRow
from app.services.demo import build_demo_files
from app.services.detector import ExpenseRecord, SaleRecord, comparison_periods, detect

PERIOD = Period(date_from=date(2026, 9, 18), date_to=date(2026, 10, 1))
PRODUCT_ID = uuid5(NAMESPACE_URL, "test/coffee")
EXPECTED = json.loads(
    (Path(__file__).resolve().parents[2] / "demo_data/taraz_expected.json").read_text("utf-8")
)


def source(day, index, amount="1000", kind="sale"):
    return SourceRow(
        record_id=uuid5(NAMESPACE_URL, f"test/{kind}/{index}"),
        import_id=uuid5(NAMESPACE_URL, kind),
        filename=f"{kind}.csv",
        source_row=index + 2,
        date=day,
        record_type=kind,
        amount=Decimal(amount),
    )


def sales_records(current_price="100", current_cost="50"):
    return [
        SaleRecord(
            source=source(PERIOD.date_from + timedelta(days=i), i),
            product_id=PRODUCT_ID,
            name="Кофе",
            quantity=Decimal("10"),
            unit_price=Decimal("100" if i < 7 else current_price),
            unit_cost=Decimal("50" if i < 7 else current_cost),
        )
        for i in range(14)
    ]


def expense_records(current="1500", kind="expense"):
    return [
        ExpenseRecord(
            source=source(
                PERIOD.date_from + timedelta(days=i), i, "1000" if i < 7 else current, kind
            ),
            category="Packaging",
            description="Упаковка",
        )
        for i in range(14)
    ]


def signal(result, kind):
    return next(s for s in result.signals if s.type == kind)


def test_demo_three_independent_scenarios():
    files = build_demo_files()
    sales = []
    expenses = []
    for i, row in enumerate(csv.DictReader(io.StringIO(files["sales"].decode()))):
        sales.append(
            SaleRecord(
                source=source(date.fromisoformat(row["date"]), i),
                product_id=uuid5(NAMESPACE_URL, row["product_id"]),
                name=row["product_name"],
                quantity=Decimal(row["quantity"]),
                unit_price=Decimal(row["unit_price"]),
                unit_cost=Decimal(row["unit_cost"]),
            )
        )
    for i, row in enumerate(csv.DictReader(io.StringIO(files["expenses"].decode()))):
        expenses.append(
            ExpenseRecord(
                source=source(date.fromisoformat(row["date"]), i, row["amount"], "expense"),
                category=row["category"],
                description=row["description"],
            )
        )
    period = Period(date_from=EXPECTED["date_from"], date_to=EXPECTED["date_to"])
    result = detect(period, sales, expenses)
    assert {s.type for s in result.signals} == {
        "EXPENSE_SPIKE",
        "MARGIN_DROP",
        "POSSIBLE_DUPLICATE",
    }
    expense = signal(result, "EXPENSE_SPIKE")
    assert expense.evidence.current_value == Decimal(EXPECTED["packaging_current_30_days"])
    assert expense.evidence.baseline_value == Decimal(EXPECTED["packaging_baseline_30_days"])
    assert expense.evidence.deviation_percent == Decimal("55.00")
    assert expense.savings == Decimal("16500.00")
    margin = signal(result, "MARGIN_DROP")
    assert margin.evidence.current_value == Decimal(EXPECTED["coffee_current_margin_percent"])
    assert margin.evidence.baseline_value == Decimal(EXPECTED["coffee_baseline_margin_percent"])
    assert margin.evidence.deviation_pp == Decimal("-37.50")
    assert margin.savings == Decimal("337500.00")
    duplicate = signal(result, "POSSIBLE_DUPLICATE")
    assert duplicate.evidence.current_value == Decimal(EXPECTED["possible_duplicate"]["amount"])
    assert duplicate.evidence.current_rows == 2
    assert duplicate.savings is None
    assert duplicate.confidence == "low"
    assert all(s.recommendation and s.evidence.source_rows for s in result.signals)


@pytest.mark.parametrize("days,window", [(1, None), (13, None), (14, 7), (30, 15), (90, 30)])
def test_comparison_windows_stay_within_requested_period(days, window):
    period = Period(date_from=date(2026, 1, 1), date_to=date(2026, 1, 1) + timedelta(days=days - 1))
    current, baseline = comparison_periods(period)
    if window is None:
        assert current is baseline is None
    else:
        assert current.date_to == period.date_to
        assert (current.date_to - current.date_from).days + 1 == window
        assert (baseline.date_to - baseline.date_from).days + 1 == window
        assert period.date_from <= baseline.date_from
        assert baseline.date_to + timedelta(days=1) == current.date_from


def test_sparse_and_zero_baseline_do_not_force_comparison_signals():
    result = detect(PERIOD, sales_records(current_price="20")[:-1], expense_records()[:2])
    assert not any(s.type in {"SALES_DROP", "EXPENSE_SPIKE"} for s in result.signals)
    assert next(c for c in result.checks if c.type == "SALES_DROP").status == "insufficient_data"
    empty = detect(PERIOD, [], [])
    assert not empty.signals
    assert all(c.status == "insufficient_data" for c in empty.checks)
    zero = [
        replace(r, source=r.source.model_copy(update={"amount": Decimal("0")})) if i < 7 else r
        for i, r in enumerate(expense_records())
    ]
    assert not any(s.type == "EXPENSE_SPIKE" for s in detect(PERIOD, [], zero).signals)


def test_missing_cost_suppresses_product_rules_but_preserves_revenue_drop():
    rows = sales_records(current_price="50", current_cost="49")
    rows = [replace(r, unit_cost=None) if i == 9 else r for i, r in enumerate(rows)]
    result = detect(PERIOD, rows, [])
    assert not any(s.type in {"MARGIN_DROP", "LOW_PROFIT_PRODUCT"} for s in result.signals)
    drop = signal(result, "SALES_DROP")
    assert drop.evidence.current_value == Decimal("3500.00")
    assert drop.evidence.baseline_value == Decimal("7000.00")
    assert drop.evidence.deviation_percent == Decimal("-50.00")
    assert drop.savings is None


def test_low_profit_rule_and_negative_margin():
    rows = sales_records(current_cost="120")
    result = detect(PERIOD, rows, [])
    low = signal(result, "LOW_PROFIT_PRODUCT")
    assert low.evidence.current_value == Decimal("15.00")
    assert low.savings is None
    negative = [replace(r, unit_cost=Decimal("120")) for r in rows]
    low = signal(detect(PERIOD, negative, []), "LOW_PROFIT_PRODUCT")
    assert low.evidence.current_value == Decimal("-20.00")
    assert low.severity == "high"


def test_returns_and_refunds_reverse_amounts_and_refunds_are_not_duplicates():
    rows = sales_records()
    refund_sale = replace(
        rows[-1], source=source(PERIOD.date_to, 100, kind="return"), quantity=Decimal("20")
    )
    result = detect(PERIOD, rows + [refund_sale], [])
    assert signal(result, "SALES_DROP").evidence.current_value == Decimal("5000.00")
    expenses = expense_records()
    refund = ExpenseRecord(
        source=source(PERIOD.date_to, 100, "3500", "refund"),
        category="Packaging",
        description="Возврат",
    )
    result = detect(PERIOD, [], expenses + [refund, refund])
    assert not result.signals


def test_duplicate_needs_nonempty_matching_description_and_preserves_provenance():
    rows = expense_records()
    duplicate = replace(
        rows[-1], source=source(PERIOD.date_to, 100, "1500", "expense"), description="  УПАКОВКА  "
    )
    result = detect(PERIOD, [], rows + [duplicate])
    found = signal(result, "POSSIBLE_DUPLICATE")
    assert {r.source_row for r in found.evidence.source_rows} == {15, 102}
    blank = [replace(r, description=" ") for r in [rows[-1], duplicate]]
    assert not detect(PERIOD, [], blank).signals


def test_expense_threshold_uses_exact_decimal_and_evidence_samples_both_windows():
    result = detect(PERIOD, [], expense_records("1250"))
    item = signal(result, "EXPENSE_SPIKE")
    assert item.evidence.deviation_percent == Decimal("25.00")
    assert item.savings == Decimal("1750.00")
    assert len(item.evidence.source_rows) == 14
    assert item.evidence.current_days == item.evidence.baseline_days == 7
    assert not detect(PERIOD, [], expense_records("1249.99")).signals


def test_rows_outside_selected_period_do_not_affect_analysis():
    rows = sales_records()
    outside = replace(
        rows[-1], unit_cost=Decimal("10000"), source=source(PERIOD.date_to + timedelta(days=1), 100)
    )
    assert not detect(PERIOD, rows + [outside], []).signals
