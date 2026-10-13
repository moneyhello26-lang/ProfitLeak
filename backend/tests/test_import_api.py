import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import Business, Expense, ImportBatch, Product, Sale
from app.services import import_store
from app.services.import_parser import MAX_UPLOAD_BYTES, parse_file
from app.services.import_store import confirm_import
from tests.test_import_parser import SALES_HEADER, VALID_SALE, xlsx_bytes

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def business(client):
    response = client.post("/api/v1/businesses", json={"name": "Taraz Cafe", "industry": "cafe"})
    assert response.status_code == 201
    return response.json()["id"]


def preview(client, business, data=None, kind="sales", filename="sales.csv"):
    return client.post(
        "/api/v1/imports/preview",
        data={"business_id": business, "kind": kind},
        files={"file": (filename, data or (SALES_HEADER + VALID_SALE).encode())},
    )


def confirm(client, business, token, data=None, kind="sales", filename="sales.csv"):
    return client.post(
        "/api/v1/imports/confirm",
        data={"business_id": business, "kind": kind, "preview_token": token},
        files={"file": (filename, data or (SALES_HEADER + VALID_SALE).encode())},
    )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_preview_confirm_and_repeat(client, business, db):
    response = preview(client, business)
    assert response.status_code == 200
    result = response.json()
    assert result["can_confirm"] is True
    assert result["preview"][0]["data"]["unit_price"] == "1200.10"
    assert count(db, Sale) == count(db, Product) == count(db, ImportBatch) == 0
    first = confirm(client, business, result["preview_token"])
    assert first.status_code == 200
    assert first.json()["already_imported"] is False
    assert first.json()["imported"]["status"] == "confirmed"
    assert count(db, Sale) == count(db, Product) == count(db, ImportBatch) == 1
    second = confirm(client, business, result["preview_token"])
    assert second.json()["already_imported"] is True
    assert second.json()["imported"]["id"] == first.json()["imported"]["id"]
    assert count(db, Sale) == 1


def test_normalized_duplicate_preview(client, business, db):
    result = preview(client, business).json()
    confirm(client, business, result["preview_token"])
    altered = (SALES_HEADER + "2026-10-01,P001, Кофе ,3.000,1200.10,450.00\n").encode()
    repeated = preview(client, business, altered, filename="renamed.csv").json()
    assert repeated["can_confirm"] is False
    assert repeated["existing_import_id"] is not None
    assert count(db, Sale) == 1


def test_file_changed_after_preview(client, business, db):
    result = preview(client, business).json()
    response = confirm(
        client,
        business,
        result["preview_token"],
        (SALES_HEADER + VALID_SALE.replace("1200.10", "1250")).encode(),
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_preview_token"
    assert count(db, Sale) == 0


def test_invalid_preview_reports_errors(client, business, db):
    response = preview(
        client, business, (SALES_HEADER + "2026-02-30,P001,Coffee,-1,NaN,5\n").encode()
    )
    assert response.status_code == 200
    assert response.json()["can_confirm"] is False
    assert response.json()["preview_token"] is None
    assert {error["field"] for error in response.json()["errors"]} == {
        "date",
        "quantity",
        "unit_price",
    }
    assert count(db, ImportBatch) == 0


def test_expense_duplicates_are_preserved(client, business, db):
    data = (
        b"date,category,description,amount\n2026-10-01,Packaging,Cups,25\n"
        + b"2026-10-01,Packaging,Cups,25\n"
    )
    result = preview(client, business, data, "expenses", "expenses.csv").json()
    response = confirm(client, business, result["preview_token"], data, "expenses", "expenses.csv")
    assert response.status_code == 200
    assert count(db, Expense) == 2


def test_products_upsert(client, business, db):
    for name in ["Coffee", "Coffee updated"]:
        data = f"product_id,name,category\nP001,{name},Drinks\n".encode()
        result = preview(client, business, data, "products", "products.csv").json()
        assert (
            confirm(
                client, business, result["preview_token"], data, "products", "products.csv"
            ).status_code
            == 200
        )
    assert count(db, Product) == 1
    assert db.scalar(select(Product)).name == "Coffee updated"


def test_xlsx_confirmation(client, business, db):
    data = xlsx_bytes(
        [SALES_HEADER.strip().split(","), ["2026-10-01", "P001", "Coffee", 1, 1200, None]]
    )
    result = preview(client, business, data, filename="sales.xlsx").json()
    response = confirm(client, business, result["preview_token"], data, filename="sales.xlsx")
    assert response.status_code == 200
    assert db.scalar(select(Sale)).unit_cost is None


def test_failed_import_rolls_back_all_records(db, monkeypatch):
    business = Business(name="Cafe", industry="cafe")
    db.add(business)
    db.flush()
    parsed = parse_file("sales.csv", (SALES_HEADER + VALID_SALE).encode(), "sales")
    original_insert = import_store.insert

    def fail_sales_insert(session, model):
        if model is Sale:
            raise RuntimeError("simulated failure after product insert")
        return original_insert(session, model)

    monkeypatch.setattr(import_store, "insert", fail_sales_insert)
    with pytest.raises(RuntimeError):
        confirm_import(db, business.id, "sales", parsed)
    assert count(db, Sale) == count(db, Product) == count(db, ImportBatch) == 0


def test_business_scope_and_import_history(client, business):
    result = preview(client, business).json()
    confirm(client, business, result["preview_token"])
    other = client.post("/api/v1/businesses", json={"name": "Other", "industry": "cafe"}).json()[
        "id"
    ]
    assert client.get("/api/v1/imports", params={"business_id": other}).json() == []
    assert len(client.get("/api/v1/imports", params={"business_id": business}).json()) == 1
    response = confirm(client, other, result["preview_token"])
    assert response.status_code == 409


def test_unknown_business(client):
    response = preview(client, "00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404


def test_oversized_request_is_rejected_before_parsing(client, business):
    response = preview(client, business, b"x" * (MAX_UPLOAD_BYTES + 100_000))
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_unsupported_file(client, business):
    response = preview(client, business, b"hello", filename="file.pdf")
    assert response.status_code == 415
