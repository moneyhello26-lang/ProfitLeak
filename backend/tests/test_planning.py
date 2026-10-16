from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db.session import get_db
from app.main import app
from app.models import Business, Expense, ImportBatch, Sale
from app.services.demo import load_demo
from app.services.import_parser import parse_file
from app.services.import_store import confirm_import

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def business(db):
    result = Business(name="Planning fixture", industry="cafe")
    db.add(result)
    db.flush()
    return result


def add_csv(db, business, kind, content):
    parsed = parse_file(f"{kind}.csv", content.encode(), kind)
    assert not parsed.errors
    return confirm_import(db, business.id, kind, parsed)


def request(client, business, endpoint="forecast", **params):
    result = client.get(
        f"/api/v1/analytics/{endpoint}",
        params={"business_id": str(business.id), **params},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.fixture
def history(db, business):
    start = date(2026, 8, 3)  # Monday, six complete weeks.
    sales = ["date,product_id,product_name,quantity,unit_price,unit_cost"]
    expenses = ["date,category,description,amount"]
    for i in range(42):
        day = start + timedelta(days=i)
        price = (day.weekday() + 1) * 100
        sales.append(f"{day},A,Coffee,1,{price},{price // 2}")
        expenses.append(f"{day},Rent,Daily rent,10")
    add_csv(db, business, "sales", "\n".join(sales))
    add_csv(db, business, "expenses", "\n".join(expenses))
    return business


def test_demo_comparison_matches_independent_totals(client, db):
    business = load_demo(db).business
    result = request(client, business, "comparison")
    assert result["current"]["period"] == {"date_from": "2026-09-02", "date_to": "2026-10-01"}
    assert result["baseline"]["period"] == {"date_from": "2026-08-03", "date_to": "2026-09-01"}
    metrics = {m["name"]: m for m in result["metrics"]}
    assert metrics["revenue"]["change"] == "0.00"
    assert metrics["operating_profit"]["baseline"]["value"] == "865500.00"
    assert metrics["operating_profit"]["current"]["value"] == "511500.00"
    assert metrics["operating_profit"]["change"] == "-354000.00"
    coffee = next(p for p in result["products"] if p["external_id"] == "P001")
    assert coffee["gross_margin_percent"]["change"] == "-37.50"
    assert coffee["gross_margin_percent"]["change_percent"] is None
    packaging = next(c for c in result["categories"] if c["category"] == "Packaging")
    assert packaging["amount"]["change"] == "16500.00"
    assert packaging["amount"]["change_percent"] == "55.00"
    assert result["current_sales_days"] == result["baseline_sales_days"] == 30
    assert len(result["points"]) == 30
    assert result["warnings"] == []


def test_comparison_unequal_periods_daily_means_and_outer_joins(client, db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost\n"
        "2026-09-01,A,Coffee,1,100,50\n2026-09-02,A,Coffee,1,100,50\n"
        "2026-09-01,B,Old,1,10,2\n2026-10-01,A,Coffee,1,100,50\n"
        "2026-10-01,C,New,0.001,1000,0\n",
    )
    add_csv(
        db,
        business,
        "expenses",
        "date,category,description,amount\n2026-09-01,Rent,Rent,10\n2026-10-01,Wages,Wages,20\n",
    )
    result = request(
        client,
        business,
        "comparison",
        date_from="2026-10-01",
        date_to="2026-10-01",
        baseline_from="2026-09-01",
        baseline_to="2026-09-02",
    )
    revenue = result["metrics"][0]
    assert revenue["change"] == "-109.00"
    assert revenue["current_per_day"] == "101.00"
    assert revenue["baseline_per_day"] == "105.00"
    assert revenue["per_day_change"] == "-4.00"
    assert revenue["per_day_change_percent"] == "-3.81"
    products = {p["external_id"]: p for p in result["products"]}
    assert products["B"]["presence"] == "baseline_only"
    assert products["C"]["presence"] == "current_only"
    assert products["B"]["revenue"]["current"]["value"] is None
    assert products["C"]["revenue"]["change"] is None
    assert products["C"]["quantity"]["current"]["value"] == "0.001"
    assert result["points"][1]["current_date"] is None
    assert result["points"][1]["current"]["value"] is None
    assert {c["presence"] for c in result["categories"]} == {"baseline_only", "current_only"}
    page = request(
        client,
        business,
        "comparison",
        date_from="2026-10-01",
        date_to="2026-10-01",
        baseline_from="2026-09-01",
        baseline_to="2026-09-02",
        products_limit=1,
        products_offset=1,
        categories_limit=1,
        categories_offset=1,
    )
    assert page["products_total"] == 3 and len(page["products"]) == 1
    assert page["products"][0] == result["products"][1]
    assert page["categories_total"] == 2 and len(page["categories"]) == 1


def test_comparison_zero_and_negative_bases_and_returns(client, db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost,record_type\n"
        "2026-09-01,A,Coffee,1,10,5,return\n2026-10-01,A,Coffee,1,5,2,sale\n",
    )
    add_csv(
        db,
        business,
        "expenses",
        "date,category,description,amount,record_type\n"
        "2026-09-01,Rent,Rent,10,expense\n2026-09-01,Rent,Refund,10,refund\n"
        "2026-10-01,Rent,Rent,5,expense\n",
    )
    params = dict(
        date_from="2026-10-01",
        date_to="2026-10-01",
        baseline_from="2026-09-01",
        baseline_to="2026-09-01",
    )
    result = request(client, business, "comparison", **params)
    metrics = {m["name"]: m for m in result["metrics"]}
    assert metrics["revenue"]["baseline"]["value"] == "-10.00"
    assert metrics["revenue"]["change_percent"] == "150.00"
    assert metrics["operating_expenses"]["baseline"]["value"] == "0.00"
    assert metrics["operating_expenses"]["change_percent"] is None
    for expense in db.scalars(select(Expense)):
        expense.amount = Decimal(0)
    db.flush()
    metrics = {m["name"]: m for m in request(client, business, "comparison", **params)["metrics"]}
    assert metrics["operating_expenses"]["change_percent"] == "0.00"


def test_comparison_empty_period_and_missing_cost_are_not_zero(client, db, history):
    sale = db.scalar(select(Sale).where(Sale.date == date(2026, 9, 13)))
    sale.unit_cost = None
    db.flush()
    result = request(
        client,
        history,
        "comparison",
        date_from="2026-09-13",
        date_to="2026-09-13",
        baseline_from="2026-01-01",
        baseline_to="2026-01-01",
    )
    assert result["baseline"]["revenue"]["value"] is None
    assert all(m["change"] is None for m in result["metrics"])
    assert result["current"]["gross_profit"]["reason"] == "missing_cost"
    assert len(result["products"]) == 1


@pytest.mark.parametrize(
    "params",
    [
        {"baseline_from": "2026-08-01"},
        {"baseline_to": "2026-08-01"},
        {"baseline_from": "2026-09-01", "baseline_to": "2026-08-01"},
        {"baseline_from": "2026-10-01", "baseline_to": "2026-10-02"},
        {"baseline_from": "2024-01-01", "baseline_to": "2026-01-01"},
        {"date_from": "0001-01-01", "date_to": "0001-01-02"},
    ],
)
def test_invalid_comparison_periods(client, business, params):
    response = client.get(
        "/api/v1/analytics/comparison",
        params={
            "business_id": str(business.id),
            "date_from": "2026-10-01",
            "date_to": "2026-10-02",
            **params,
        },
    )
    assert response.status_code == 400


def test_forecast_weekday_pattern_exact_financial_identity_and_backtest(client, history):
    result = request(client, history, horizon_days=7)
    assert result["status"] == "available"
    assert result["forecast_period"] == {"date_from": "2026-09-14", "date_to": "2026-09-20"}
    assert result["training_days"] == result["observed_sales_days"] == 30
    assert [p["revenue"]["value"] for p in result["points"]] == [
        f"{i * 100}.00" for i in range(1, 8)
    ]
    expected = dict(
        revenue="2800.00",
        cogs="1400.00",
        gross_profit="1400.00",
        gross_margin_percent="50.00",
        operating_expenses="70.00",
        operating_profit="1330.00",
    )
    for name, value in expected.items():
        assert result["totals"][name]["value"] == value
    for p in result["points"]:
        assert Decimal(p["operating_profit"]["value"]) == (
            Decimal(p["revenue"]["value"])
            - Decimal(p["cogs"]["value"])
            - Decimal(p["operating_expenses"]["value"])
        )
    assert result["backtest"]["revenue_mae"] == "0.00"
    assert result["backtest"]["revenue_wape_percent"] == "0.00"
    assert (
        result["backtest"]["training_period"]["date_to"]
        < result["backtest"]["test_period"]["date_from"]
    )


def test_forecast_scenario_changes_only_intended_components(client, history):
    result = request(
        client, history, horizon_days=7, sales_change_percent="10", expense_change_percent="20"
    )
    totals = result["totals"]
    assert totals["revenue"]["value"] == "3080.00"
    assert totals["cogs"]["value"] == "1540.00"
    assert totals["operating_expenses"]["value"] == "84.00"
    assert totals["operating_profit"]["value"] == "1456.00"
    assert result["baseline_totals"]["revenue"]["value"] == "2800.00"
    assert result["backtest"]["revenue_mae"] == "0.00"


def test_demo_forecast_recent_cost_structure_and_monthly_rent(client, db):
    business = load_demo(db).business
    result = request(client, business, horizon_days=30)
    assert result["status"] == "available"
    assert result["totals"]["revenue"]["value"] == "1818000.00"
    assert result["totals"]["cogs"]["value"] == "1050000.00"
    assert result["totals"]["operating_expenses"]["value"] == "256500.00"
    assert result["totals"]["operating_profit"]["value"] == "511500.00"


def test_forecast_net_sales_returns_and_expense_refunds(client, db, history):
    sales = ["date,product_id,product_name,quantity,unit_price,unit_cost,record_type"]
    expenses = ["date,category,description,amount,record_type"]
    for i in range(42):
        day = date(2026, 8, 3) + timedelta(days=i)
        price = (day.weekday() + 1) * 100
        sales.append(f"{day},A,Coffee,0.5,{price},{price // 2},return")
        expenses.append(f"{day},Rent,Partial refund,2,refund")
    add_csv(db, history, "sales", "\n".join(sales))
    add_csv(db, history, "expenses", "\n".join(expenses))
    result = request(client, history, horizon_days=7)
    assert result["totals"]["revenue"]["value"] == "1400.00"
    assert result["totals"]["cogs"]["value"] == "700.00"
    assert result["totals"]["operating_expenses"]["value"] == "56.00"
    assert result["totals"]["operating_profit"]["value"] == "644.00"
    assert result["backtest"]["revenue_mae"] == "0.00"


def test_forecast_minimum_history_and_no_future_data_leak(client, db, history):
    # Even though later records exist, neither fit nor validation can use them.
    result = request(client, history, date_from="2026-08-03", date_to="2026-08-30", horizon_days=7)
    assert result["training_days"] == 28
    assert result["status"] == "available"
    assert result["backtest"]["status"] == "insufficient_data"
    assert result["forecast_period"]["date_from"] == "2026-08-31"
    db.scalar(select(Sale).where(Sale.date == date(2026, 8, 31))).unit_price = Decimal("99999")
    db.flush()
    after = request(client, history, date_from="2026-08-03", date_to="2026-08-30", horizon_days=7)
    assert after == result


def test_forecast_large_amounts_keep_precision(client, db, history):
    for sale in db.scalars(select(Sale)):
        sale.quantity = Decimal("999999999999999.999")
        sale.unit_price = Decimal("9999999999999999.99")
        sale.unit_cost = Decimal("0.00")
    db.flush()
    result = request(client, history, horizon_days=7)
    assert result["points"][0]["revenue"]["value"] == "9999999999999999980000000000000.00"
    assert result["totals"]["revenue"]["value"] == "69999999999999999860000000000000.00"


def test_forecast_missing_calendar_requires_explicit_confirmation(client, db, history):
    missing_day = date(2026, 9, 13)
    db.execute(delete(Sale).where(Sale.date == missing_day))
    db.flush()
    result = request(client, history, horizon_days=7)
    assert result["totals"]["revenue"]["reason"] == "incomplete_sales_calendar"
    assert result["totals"]["operating_expenses"]["value"] == "70.00"
    assert result["status"] == "partial"
    assert result["history"][-1]["revenue"]["value"] is None
    confirmed = request(client, history, horizon_days=7, complete_calendar=True)
    assert confirmed["status"] == "available"
    assert confirmed["history"][-1]["revenue"]["value"] == "0.00"
    assert confirmed["points"][-1]["revenue"]["value"] == "560.00"
    assert confirmed["totals"]["revenue"]["value"] == "2660.00"


def test_forecast_missing_cost_does_not_invent_profit(client, db, history):
    db.scalar(select(Sale).where(Sale.date == date(2026, 9, 13))).unit_cost = None
    db.flush()
    result = request(client, history, horizon_days=7, complete_calendar=True)
    assert result["totals"]["revenue"]["value"] == "2800.00"
    for name in ("cogs", "gross_profit", "gross_margin_percent", "operating_profit"):
        assert result["totals"][name]["reason"] == "missing_cost"
        assert result["totals"][name]["value"] is None


def test_forecast_sparse_expenses_and_absent_imports(client, db, history):
    db.execute(delete(Expense).where(Expense.date != date(2026, 9, 13)))
    db.flush()
    result = request(client, history, horizon_days=7)
    assert result["totals"]["operating_expenses"]["reason"] == "incomplete_expense_calendar"
    assert result["totals"]["operating_profit"]["value"] is None
    confirmed = request(client, history, horizon_days=7, complete_calendar=True)
    assert confirmed["totals"]["operating_expenses"]["value"] == "2.31"
    batch = db.scalar(select(ImportBatch).where(ImportBatch.kind == "expenses"))
    batch.status = "processing"
    db.flush()
    unconfirmed = request(client, history, horizon_days=7, complete_calendar=True)
    assert unconfirmed["totals"]["operating_expenses"]["reason"] == "no_expenses"
    assert unconfirmed["observed_expense_days"] == 0


def test_forecast_does_not_train_on_holdout_week(client, db, history):
    for sale in db.scalars(select(Sale).where(Sale.date >= date(2026, 9, 7))):
        sale.unit_price *= 2
    db.flush()
    result = request(client, history, horizon_days=7)
    assert result["backtest"]["revenue_mae"] == "400.00"
    assert result["backtest"]["revenue_wape_percent"] == "50.00"


def test_forecast_confirmed_zero_holdout_week_is_evaluated(client, db, history):
    db.execute(delete(Sale).where(Sale.date >= date(2026, 9, 7)))
    db.flush()
    result = request(client, history, horizon_days=7, complete_calendar=True)
    assert result["backtest"]["status"] == "available"
    assert result["backtest"]["revenue_mae"] == "400.00"
    assert result["backtest"]["revenue_wape_percent"] is None


def test_forecast_short_and_empty_data_are_unavailable(client, business, history):
    result = request(client, history, date_from="2026-09-07", date_to="2026-09-13", horizon_days=7)
    assert result["status"] == "insufficient_data"
    assert result["totals"]["revenue"]["reason"] == "insufficient_history"
    assert result["backtest"]["status"] == "insufficient_data"
    empty = request(
        client, business, date_from="2020-01-01", date_to="2020-02-11", complete_calendar=True
    )
    assert empty["totals"]["revenue"]["reason"] == "no_sales"
    assert empty["totals"]["operating_expenses"]["reason"] == "no_expenses"


def test_forecast_zero_revenue_zero_expenses_and_returns(client, db, history):
    for sale in db.scalars(select(Sale)):
        sale.unit_price = Decimal(0)
        sale.unit_cost = Decimal(0)
        sale.record_type = "return"
    for expense in db.scalars(select(Expense)):
        expense.amount = Decimal(0)
        expense.record_type = "refund"
    db.flush()
    result = request(client, history, horizon_days=7)
    assert result["totals"]["revenue"]["value"] == "0.00"
    assert result["totals"]["operating_profit"]["value"] == "0.00"
    assert result["totals"]["gross_margin_percent"]["reason"] == "zero_revenue"
    assert result["backtest"]["revenue_mae"] == "0.00"
    assert result["backtest"]["revenue_wape_percent"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"horizon_days": 0},
        {"horizon_days": 91},
        {"sales_change_percent": 101},
        {"sales_change_percent": -51},
        {"expense_change_percent": "0.001"},
        {"expense_change_percent": "NaN"},
    ],
)
def test_invalid_forecast_options(client, business, params):
    response = client.get(
        "/api/v1/analytics/forecast", params={"business_id": str(business.id), **params}
    )
    assert response.status_code == 422


def test_forecast_date_overflow_is_a_client_error(client, business):
    response = client.get(
        "/api/v1/analytics/forecast",
        params={
            "business_id": str(business.id),
            "date_from": "9999-12-01",
            "date_to": "9999-12-31",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_forecast"


@pytest.mark.parametrize("endpoint", ["forecast", "comparison"])
def test_planning_unknown_business_and_tenant_isolation(client, db, history, endpoint):
    response = client.get(f"/api/v1/analytics/{endpoint}", params={"business_id": str(uuid4())})
    assert response.status_code == 404
    other = Business(name="Other", industry="cafe")
    db.add(other)
    db.flush()
    result = request(client, other, endpoint)
    if endpoint == "comparison":
        assert result["products"] == [] and result["categories"] == []
        assert result["current"]["revenue"]["value"] is None
    else:
        assert result["status"] == "insufficient_data"
        assert result["totals"]["revenue"]["value"] is None
