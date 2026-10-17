from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Business, Expense, ImportBatch, Insight, Product, Sale

pytestmark = pytest.mark.integration


@pytest.fixture
def records(db):
    business = Business(name="Taraz Cafe", industry="cafe")
    other_business = Business(name="Other Cafe", industry="cafe")
    db.add_all([business, other_business])
    db.flush()
    product = Product(business_id=business.id, external_id="P001", name="Coffee")
    batch = ImportBatch(
        business_id=business.id, filename="sales.csv", kind="sales", file_sha256="a" * 64
    )
    other_product = Product(business_id=other_business.id, external_id="P001", name="Coffee")
    other_batch = ImportBatch(
        business_id=other_business.id, filename="sales.csv", kind="sales", file_sha256="a" * 64
    )
    db.add_all([product, batch, other_product, other_batch])
    db.flush()
    return business, product, batch, other_product, other_batch


def make_sale(records, **values):
    business, product, batch, _, _ = records
    data = dict(
        business_id=business.id,
        product_id=product.id,
        import_id=batch.id,
        source_row=2,
        date=date(2026, 10, 1),
        quantity=Decimal("3.000"),
        unit_price=Decimal("0.10"),
        unit_cost=Decimal("0.03"),
    )
    data.update(values)
    return Sale(**data)


def test_migration_matches_models(database_connection):
    context = MigrationContext.configure(database_connection, opts={"compare_type": True})
    assert compare_metadata(context, Base.metadata) == []


def test_exact_money_and_unknown_cost(db, records):
    db.add(make_sale(records))
    db.add(make_sale(records, source_row=3, unit_cost=None))
    db.flush()
    amount = sum(row.quantity * row.unit_price for row in db.scalars(select(Sale)))
    assert isinstance(amount, Decimal)
    assert amount == Decimal("0.60")
    assert db.scalar(select(Sale.unit_cost).where(Sale.source_row == 3)) is None


def test_large_money_round_trip_is_exact_and_sqlite_storage_uses_integers(db, records):
    price = Decimal("90071992547409.93")
    db.add(make_sale(records, unit_price=price, quantity=Decimal("0.001")))
    db.flush()
    row = db.scalar(select(Sale))
    assert row.unit_price == price
    assert row.quantity == Decimal("0.001")
    assert row.created_at.tzinfo is not None
    if db.get_bind().dialect.name == "sqlite":
        raw = db.execute(text("SELECT unit_price, quantity, typeof(unit_price) FROM sales")).one()
        assert raw == (9007199254740993, 1, "integer")


@pytest.mark.parametrize("field", ["product_id", "import_id"])
def test_cross_business_references_are_rejected(db, records, field):
    value = records[3].id if field == "product_id" else records[4].id
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(make_sale(records, **{field: value}))
        db.flush()


@pytest.mark.parametrize(
    "values",
    [
        {"quantity": Decimal("-1")},
        {"quantity": Decimal("0")},
        {"unit_price": Decimal("-0.01")},
        {"unit_cost": Decimal("-0.01")},
        {"unit_price": Decimal("NaN")},
        {"record_type": "adjustment"},
        {"source_row": 0},
    ],
)
def test_invalid_sales_are_rejected(db, records, values):
    with pytest.raises((IntegrityError, StatementError)), db.begin_nested():
        db.add(make_sale(records, **values))
        db.flush()


def test_duplicate_import_is_rejected(db, records):
    business = records[0]
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            ImportBatch(
                business_id=business.id, filename="renamed.csv", kind="sales", file_sha256="a" * 64
            )
        )
        db.flush()


def test_invalid_content_digest_is_rejected(db, records):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            ImportBatch(
                business_id=records[0].id,
                filename="new.csv",
                kind="sales",
                file_sha256="c" * 64,
                content_sha256="not-a-digest",
            )
        )
        db.flush()


def test_duplicate_source_row_is_rejected(db, records):
    db.add(make_sale(records))
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(make_sale(records))
        db.flush()


def test_same_expense_values_on_different_rows_are_allowed(db, records):
    business = records[0]
    batch = ImportBatch(
        business_id=business.id, filename="expenses.csv", kind="expenses", file_sha256="b" * 64
    )
    db.add(batch)
    db.flush()
    for row in [2, 3]:
        db.add(
            Expense(
                business_id=business.id,
                import_id=batch.id,
                source_row=row,
                date=date(2026, 10, 1),
                category="Packaging",
                description="Paper cups",
                amount=Decimal("100.00"),
            )
        )
    db.flush()
    assert db.scalar(select(func.count()).select_from(Expense)) == 2


@pytest.mark.parametrize("estimate_type", [None, "guaranteed"])
def test_savings_require_scenario_label(db, records, estimate_type):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            Insight(
                business_id=records[0].id,
                type="EXPENSE_SPIKE",
                severity="medium",
                confidence="medium",
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
                evidence_json={"category": "Packaging"},
                estimated_savings=Decimal("25.00"),
                estimate_type=estimate_type,
                recommendation="Check packaging purchase prices.",
            )
        )
        db.flush()


def test_health_with_database(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_migration_downgrade_and_upgrade(database_connection):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["connection"] = database_connection
    with database_connection.begin_nested():
        command.downgrade(config, "base")
        assert inspect(database_connection).get_table_names() == ["alembic_version"]
        command.upgrade(config, "head")
        assert set(inspect(database_connection).get_table_names()) == {
            "alembic_version",
            "businesses",
            "products",
            "imports",
            "sales",
            "expenses",
            "insights",
            "analysis_runs",
            "users",
            "user_sessions",
            "business_memberships",
            "account_bootstrap",
            "cash_accounts",
            "cash_entries",
            "planned_payments",
            "cash_budgets",
        }
