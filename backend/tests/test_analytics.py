from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models import Business, ImportBatch, Sale
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
    business = Business(name="Fixture cafe", industry="cafe")
    db.add(business)
    db.flush()
    return business


def add_csv(db, business, kind, text):
    return confirm_import(db, business.id, kind, parse_file(f"{kind}.csv", text.encode(), kind))


@pytest.fixture
def data(db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost,"
        "record_type\n2026-10-01,A,Coffee,3,0.10,0.03,sale\n"
        "2026-10-02,A,Coffee,1,0.10,0.03,return\n"
        "2026-10-01,B,Tea,2.5,10,4,sale\n",
    )
    add_csv(
        db,
        business,
        "expenses",
        "date,category,description,amount,record_type\n"
        "2026-10-01,Packaging,Cups,2.25,expense\n"
        "2026-10-01,Packaging,Refund,0.25,refund\n"
        "2026-10-02,Wages,Wages,3.00,expense\n",
    )
    return business


def query(client, business, endpoint="/dashboard/summary", **overrides):
    params = {"business_id": str(business.id), "date_from": "2026-10-01", "date_to": "2026-10-02"}
    params.update(overrides)
    response = client.get("/api/v1" + endpoint, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_hand_calculated_kpis_and_tenant_isolation(client, db, data):
    other = Business(name="Other cafe", industry="cafe")
    db.add(other)
    db.flush()
    add_csv(
        db,
        other,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost\n"
        "2026-10-01,A,Other coffee,1,100000,50000\n",
    )
    result = query(client, data)
    expected = {
        "revenue": "25.20",
        "cogs": "10.06",
        "gross_profit": "15.14",
        "gross_margin_percent": "60.08",
        "operating_expenses": "5.00",
        "operating_profit": "10.14",
    }
    for name, value in expected.items():
        assert result[name] == {"value": value, "status": "available", "reason": None}
    assert result["sales_rows"] == 3
    assert result["expense_rows"] == 3
    assert result["missing_cost_rows"] == 0


def test_revenue_series_filters_and_missing_days(client, data):
    result = query(client, data, "/analytics/revenue", date_to="2026-10-03")
    assert [point["date"] for point in result["points"]] == [
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
    ]
    assert [point["revenue"]["value"] for point in result["points"]] == ["25.30", "-0.10", None]
    assert result["points"][2]["revenue"]["reason"] == "no_sales"
    filtered = query(client, data, date_from="2026-10-02")
    assert filtered["revenue"]["value"] == "-0.10"
    assert filtered["operating_expenses"]["value"] == "3.00"


def test_category_totals_include_refunds(client, data):
    result = query(client, data, "/analytics/expenses")
    assert result["total"]["value"] == "5.00"
    assert result["categories"] == [
        {"category": "Wages", "amount": "3.00", "expense_rows": 1},
        {"category": "Packaging", "amount": "2.00", "expense_rows": 2},
    ]


def test_product_profits_and_pagination(client, data):
    result = query(client, data, "/analytics/products", limit=1)
    assert result["total"] == 2
    assert result["items"][0]["external_id"] == "B"
    assert result["items"][0]["gross_profit"]["value"] == "15.00"
    second = query(client, data, "/analytics/products", limit=1, offset=1)["items"][0]
    assert second["external_id"] == "A"
    assert second["net_quantity"] == "2.000"
    assert second["revenue"]["value"] == "0.20"
    assert second["cogs"]["value"] == "0.06"
    assert second["gross_margin_percent"]["value"] == "70.00"
    assert query(client, data, "/analytics/products", offset=2)["items"] == []


def test_missing_cost_does_not_become_zero(client, db, data):
    sale = db.scalar(select(Sale).where(Sale.business_id == data.id, Sale.quantity == 2.5))
    sale.unit_cost = None
    db.flush()
    result = query(client, data)
    assert result["revenue"]["value"] == "25.20"
    assert result["missing_cost_rows"] == 1
    for name in ["cogs", "gross_profit", "gross_margin_percent", "operating_profit"]:
        assert result[name] == {
            "value": None,
            "status": "insufficient_data",
            "reason": "missing_cost",
        }
    products = query(client, data, "/analytics/products")["items"]
    assert products[0]["external_id"] == "A"
    assert products[0]["gross_profit"]["value"] == "0.14"
    assert products[1]["gross_profit"]["reason"] == "missing_cost"


def test_empty_dataset_is_insufficient(client, business):
    result = query(client, business)
    assert result["sales_rows"] == 0
    assert result["revenue"]["reason"] == "no_sales"
    assert result["operating_expenses"]["reason"] == "no_expenses"
    assert result["operating_profit"]["value"] is None
    assert query(client, business, "/analytics/products")["items"] == []
    assert query(client, business, "/analytics/expenses")["categories"] == []


def test_unconfirmed_import_is_excluded(client, db, data):
    batch = db.scalar(
        select(ImportBatch).where(ImportBatch.business_id == data.id, ImportBatch.kind == "sales")
    )
    batch.status = "processing"
    db.flush()
    result = query(client, data)
    assert result["sales_rows"] == 0
    assert result["revenue"]["reason"] == "no_sales"
    assert result["operating_expenses"]["value"] == "5.00"
    assert query(client, data, "/analytics/products")["items"] == []


def test_zero_revenue_and_absent_expenses(client, db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost\n2026-10-01,A,Coffee,1,0,0\n",
    )
    result = query(client, business)
    assert result["revenue"]["value"] == "0.00"
    assert result["gross_profit"]["value"] == "0.00"
    assert result["gross_margin_percent"] == {
        "value": None,
        "status": "not_applicable",
        "reason": "zero_revenue",
    }
    assert result["operating_profit"]["reason"] == "no_expenses"


def test_expense_only_dataset(client, db, business):
    add_csv(
        db, business, "expenses", "date,category,description,amount\n2026-10-01,Rent,Rent,100\n"
    )
    result = query(client, business)
    assert result["operating_expenses"]["value"] == "100.00"
    assert result["operating_profit"]["reason"] == "no_sales"


def test_line_rounding_keeps_totals_additive(client, db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost\n"
        "2026-10-01,A,Coffee,0.5,0.01,0.01\n"
        "2026-10-01,A,Coffee,0.5,0.01,0.01\n",
    )
    assert query(client, business)["revenue"]["value"] == "0.02"
    assert query(client, business)["cogs"]["value"] == "0.02"


def test_large_supported_values_keep_all_digits(client, db, business):
    add_csv(
        db,
        business,
        "sales",
        "date,product_id,product_name,quantity,unit_price,unit_cost\n"
        "2026-10-01,A,Coffee,999999999999999.999,9999999999999999.99,0\n",
    )
    assert query(client, business)["revenue"]["value"] == "9999999999999999980000000000000.00"


@pytest.mark.parametrize(
    "date_from,date_to",
    [
        ("2026-10-02", "2026-10-01"),
        ("2026-01-01", "2027-01-02"),
        ("9999-12-31", None),
        (None, "0001-01-01"),
    ],
)
def test_invalid_period(client, business, date_from, date_to):
    params = {"business_id": str(business.id)}
    if date_from is not None:
        params["date_from"] = date_from
    if date_to is not None:
        params["date_to"] = date_to
    response = client.get("/api/v1/dashboard/summary", params=params)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_period"


def test_default_and_partial_periods(client, data):
    result = client.get("/api/v1/dashboard/summary", params={"business_id": str(data.id)}).json()
    assert result["period"] == {"date_from": "2026-07-05", "date_to": "2026-10-02"}
    result = client.get(
        "/api/v1/dashboard/summary", params={"business_id": str(data.id), "date_from": "2026-10-01"}
    ).json()
    assert result["period"] == {"date_from": "2026-10-01", "date_to": "2026-12-29"}
    result = client.get(
        "/api/v1/dashboard/summary", params={"business_id": str(data.id), "date_to": "2026-10-02"}
    ).json()
    assert result["period"]["date_from"] == "2026-07-05"


@pytest.mark.parametrize(
    "endpoint",
    ["/dashboard/summary", "/analytics/revenue", "/analytics/expenses", "/analytics/products"],
)
def test_unknown_business(client, endpoint):
    response = client.get("/api/v1" + endpoint, params={"business_id": str(uuid4())})
    assert response.status_code == 404


def test_full_366_day_period_is_supported(client, business):
    result = query(
        client, business, "/analytics/revenue", date_from="2026-01-01", date_to="2027-01-01"
    )
    assert len(result["points"]) == 366
    assert date.fromisoformat(result["points"][-1]["date"]) == date(2027, 1, 1)
