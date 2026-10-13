from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import AnalysisRun, Business, Expense, ImportBatch, Insight
from app.services import insights
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
def demo(db):
    return load_demo(db).business


def analyze(client, business, **period):
    result = client.post("/api/v1/analysis/run", json={"business_id": str(business.id), **period})
    assert result.status_code == 200, result.text
    return result.json()


def listing(client, business, **params):
    result = client.get("/api/v1/insights", params={"business_id": str(business.id), **params})
    assert result.status_code == 200, result.text
    return result.json()


def test_demo_analysis_provenance_repeatability_and_detail(client, db, demo):
    assert listing(client, demo)["analysis"] is None
    first = analyze(client, demo)
    assert first["insight_count"] == 3
    assert first["current_period"] == {"date_from": "2026-09-02", "date_to": "2026-10-01"}
    assert first["baseline_period"] == {"date_from": "2026-08-03", "date_to": "2026-09-01"}
    initial = listing(client, demo)
    assert initial["total"] == 3
    ids = {item["id"] for item in initial["items"]}
    second = analyze(client, demo)
    assert first["id"] == second["id"]
    assert ids == {item["id"] for item in listing(client, demo)["items"]}
    assert db.scalar(select(func.count()).select_from(Insight)) == 3
    assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 1
    for item in initial["items"]:
        detail = client.get(f"/api/v1/insights/{item['id']}", params={"business_id": demo.id})
        assert detail.status_code == 200
        assert detail.json()["evidence"] == item["evidence"]
        assert item["recommendation_source"] == "template"
        assert item["recommendation"]
        for row in item["evidence"]["source_rows"]:
            batch = db.get(ImportBatch, UUID(row["import_id"]))
            assert batch.business_id == demo.id and batch.status == "confirmed"
            assert batch.filename == row["filename"]
    duplicate = next(item for item in initial["items"] if item["type"] == "POSSIBLE_DUPLICATE")
    assert duplicate["potential_savings_kzt"] is duplicate["estimate_type"] is None
    assert len({row["record_id"] for row in duplicate["evidence"]["source_rows"]}) == 2
    spike = next(item for item in initial["items"] if item["type"] == "EXPENSE_SPIKE")
    assert spike["potential_savings_kzt"] == "16500.00"
    assert spike["estimate_type"] == "scenario"
    margin = next(item for item in initial["items"] if item["type"] == "MARGIN_DROP")
    assert margin["potential_savings_kzt"] == "337500.00"


def test_filters_pagination_period_scope_and_tenant_isolation(client, db, demo):
    analyze(client, demo)
    assert listing(client, demo, severity="high")["total"] == 2
    assert listing(client, demo, type="POSSIBLE_DUPLICATE")["total"] == 1
    pages = [listing(client, demo, limit=1, offset=i)["items"][0]["id"] for i in range(3)]
    assert len(set(pages)) == 3
    other = Business(name="Other", industry="retail")
    db.add(other)
    db.flush()
    assert listing(client, other)["total"] == 0
    foreign = client.get(f"/api/v1/insights/{pages[0]}", params={"business_id": other.id})
    assert foreign.status_code == 404
    analyze(client, other)
    assert listing(client, demo)["total"] == 3
    short = analyze(client, demo, date_from="2026-10-01", date_to="2026-10-01")
    assert short["insight_count"] == 1
    assert short["current_period"] is None
    assert listing(client, demo, date_from="2026-10-01", date_to="2026-10-01")["total"] == 1
    assert listing(client, demo)["total"] == 3


def test_stale_analysis_after_new_import_and_recalculation(client, db, demo):
    analyze(client, demo)
    assert listing(client, demo)["analysis"]["stale"] is False
    content = b"date,category,description,amount\n2026-10-01,Packaging,New purchase,100.00\n"
    confirm_import(db, demo.id, "expenses", parse_file("new.csv", content, "expenses"))
    assert listing(client, demo)["analysis"]["stale"] is True
    analyze(client, demo)
    result = listing(client, demo)
    assert result["analysis"]["stale"] is False
    spike = next(item for item in result["items"] if item["type"] == "EXPENSE_SPIKE")
    assert spike["evidence"]["current_value"] == "46600.00"


def test_processing_import_is_excluded_and_empty_run_is_persisted(client, db):
    business = Business(name="Empty", industry="cafe")
    db.add(business)
    db.flush()
    batch = ImportBatch(
        business_id=business.id,
        filename="unfinished.csv",
        kind="expenses",
        status="processing",
        file_sha256="c" * 64,
    )
    db.add(batch)
    db.flush()
    for row in (2, 3):
        db.add(
            Expense(
                business_id=business.id,
                import_id=batch.id,
                source_row=row,
                date=date(2026, 10, 1),
                category="Packaging",
                description="Same",
                amount=Decimal("100"),
            )
        )
    db.flush()
    result = analyze(client, business, date_from="2026-09-01", date_to="2026-10-01")
    assert result["insight_count"] == 0
    assert all(check["status"] == "insufficient_data" for check in result["checks"])
    assert listing(client, business, date_from="2026-09-01", date_to="2026-10-01")["analysis"]


@pytest.mark.parametrize(
    "dates",
    [
        {"date_from": "2026-10-02", "date_to": "2026-10-01"},
        {"date_from": "2025-01-01", "date_to": "2026-10-01"},
    ],
)
def test_bad_periods_rejected(client, demo, dates):
    result = client.post("/api/v1/analysis/run", json={"business_id": str(demo.id), **dates})
    assert result.status_code == 400


def test_unknown_business_bad_filter_and_unknown_insight(client, demo):
    assert (
        client.post("/api/v1/analysis/run", json={"business_id": str(uuid4())}).status_code == 404
    )
    assert (
        client.get(
            "/api/v1/insights", params={"business_id": demo.id, "severity": "bad"}
        ).status_code
        == 422
    )
    assert (
        client.get(f"/api/v1/insights/{uuid4()}", params={"business_id": demo.id}).status_code
        == 404
    )


def test_analysis_failure_preserves_previous_snapshot(db, demo, monkeypatch):
    from app.schemas.analytics import Period

    period = Period(date_from="2026-07-04", date_to="2026-10-01")
    first = insights.run_analysis(db, demo.id, period)
    previous_ids = set(db.scalars(select(Insight.id)))
    original = db.flush

    def fail_flush(*args, **kwargs):
        if any(isinstance(item, Insight) for item in db.new):
            raise RuntimeError("Simulated persistence failure")
        return original(*args, **kwargs)

    with pytest.raises(RuntimeError), db.begin_nested():
        monkeypatch.setattr(db, "flush", fail_flush)
        insights.run_analysis(db, demo.id, period)
    monkeypatch.setattr(db, "flush", original)
    assert set(db.scalars(select(Insight.id))) == previous_ids
    assert db.get(AnalysisRun, first.id).result_json["insight_count"] == 3
