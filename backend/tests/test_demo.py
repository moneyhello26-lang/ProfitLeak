import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text

from app.db.session import get_db, make_engine
from app.main import app
from app.models import Business, Expense, ImportBatch, Sale, User
from app.services import demo
from app.services.demo import DEMO_BUSINESS_ID, build_demo_files, load_demo
from app.services.import_parser import parse_file

EXPECTED = json.loads(
    (Path(__file__).resolve().parents[2] / "demo_data" / "taraz_expected.json").read_text(
        encoding="utf-8"
    )
)


def test_deterministic_valid_demo_files():
    first = build_demo_files()
    assert first == build_demo_files()
    for kind, content in first.items():
        parsed = parse_file("demo.csv", content, kind)
        assert parsed.errors == []
        if kind in ("sales", "expenses"):
            assert min(row.data.date.isoformat() for row in parsed.rows) == EXPECTED["date_from"]
            assert max(row.data.date.isoformat() for row in parsed.rows) == EXPECTED["date_to"]
            assert len(parsed.rows) == EXPECTED["sales_rows" if kind == "sales" else "expense_rows"]


@pytest.mark.integration
def test_load_twice_and_expected_financial_results(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            first = client.post("/api/v1/demo/load")
            assert first.status_code == 200
            assert first.json()["business"]["is_demo"] is True
            assert first.json()["already_loaded"] is False
            second = client.post("/api/v1/demo/load")
            assert second.json()["already_loaded"] is True
            for field in ["sales_rows", "expense_rows", "product_count"]:
                assert first.json()[field] == second.json()[field] == EXPECTED[field]
            assert db.scalar(select(func.count()).select_from(ImportBatch)) == 3
            params = {"business_id": first.json()["business"]["id"]}
            summary = client.get("/api/v1/dashboard/summary", params=params).json()
            assert summary["period"] == {
                "date_from": EXPECTED["date_from"],
                "date_to": EXPECTED["date_to"],
            }
            for field in [
                "revenue",
                "cogs",
                "gross_profit",
                "gross_margin_percent",
                "operating_expenses",
                "operating_profit",
            ]:
                assert summary[field]["value"] == EXPECTED[field]
            revenue = client.get("/api/v1/analytics/revenue", params=params).json()
            assert len(revenue["points"]) == 90
            assert all(point["revenue"]["value"] == "60600.00" for point in revenue["points"])
            for label, start, end in [
                ("baseline", "2026-08-03", "2026-09-01"),
                ("current", "2026-09-02", "2026-10-01"),
            ]:
                period = dict(params, date_from=start, date_to=end)
                categories = client.get("/api/v1/analytics/expenses", params=period).json()
                packaging = next(
                    item for item in categories["categories"] if item["category"] == "Packaging"
                )
                assert packaging["amount"] == EXPECTED[f"packaging_{label}_30_days"]
                products = client.get("/api/v1/analytics/products", params=period).json()
                coffee = next(item for item in products["items"] if item["external_id"] == "P001")
                assert (
                    coffee["gross_margin_percent"]["value"]
                    == EXPECTED[f"coffee_{label}_margin_percent"]
                )
        duplicate = EXPECTED["possible_duplicate"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(Expense)
                .where(
                    Expense.business_id == UUID(first.json()["business"]["id"]),
                    Expense.date == date.fromisoformat(duplicate["date"]),
                    Expense.category == duplicate["category"],
                    Expense.description == duplicate["description"],
                    Expense.amount == Decimal(duplicate["amount"]),
                )
            )
            == 2
        )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_demo_failure_rolls_back_business_and_imports(db, monkeypatch):
    original = demo.confirm_import

    def fail_expenses(session, business_id, kind, parsed):
        if kind == "expenses":
            raise RuntimeError("Simulated failure")
        return original(session, business_id, kind, parsed)

    monkeypatch.setattr(demo, "confirm_import", fail_expenses)
    with pytest.raises(RuntimeError):
        load_demo(db)
    assert db.get(Business, DEMO_BUSINESS_ID) is None
    assert db.scalar(select(func.count()).select_from(ImportBatch)) == 0
    assert db.scalar(select(func.count()).select_from(Sale)) == 0


@pytest.mark.integration
def test_personal_demos_remain_marked_for_distinct_accounts(db):
    users = [
        User(email=f"demo-{index}@example.test", full_name="Demo account", password_hash="test")
        for index in range(2)
    ]
    ordinary = Business(name="My cafe", industry="cafe")
    db.add_all([*users, ordinary])
    db.flush()
    first, second = [load_demo(db, user.id) for user in users]
    assert first.business.id != second.business.id
    assert first.business.id != DEMO_BUSINESS_ID
    assert first.business.is_demo is True
    assert second.business.is_demo is True
    assert ordinary.is_demo is False
    repeated = load_demo(db, users[0].id)
    assert repeated.already_loaded is True
    assert repeated.business.id == first.business.id
    assert repeated.business.is_demo is True


@pytest.mark.integration
def test_demo_marker_migration_marks_only_legacy_demo(tmp_path):
    engine = make_engine("sqlite:///" + (tmp_path / "legacy.db").as_posix())
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    normal_id = uuid4()
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0004")
            connection.execute(
                text("INSERT INTO businesses (id, name, industry) VALUES (:id, :name, 'cafe')"),
                [
                    {"id": DEMO_BUSINESS_ID.hex, "name": "Legacy demo"},
                    {"id": normal_id.hex, "name": "Real business"},
                ],
            )
            command.upgrade(config, "0005")
            markers = dict(connection.execute(text("SELECT id, is_demo FROM businesses")).all())
            assert markers == {DEMO_BUSINESS_ID.hex: 1, normal_id.hex: 0}
            command.downgrade(config, "0004")
            assert "is_demo" not in {
                column["name"] for column in inspect(connection).get_columns("businesses")
            }
            assert connection.scalar(text("SELECT count(*) FROM businesses")) == 2
    finally:
        engine.dispose()
