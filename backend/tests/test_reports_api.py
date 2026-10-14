from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select

from app.db.session import get_db
from app.main import app
from app.models import AnalysisRun, Business, Sale
from app.services import advisor, insights
from app.services.demo import load_demo
from app.services.import_parser import parse_file
from app.services.import_store import confirm_import


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(advisor, "request_llm", lambda *args: pytest.fail("PDF called LLM"))
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def read_pdf(client, business, **period):
    response = client.get("/api/v1/reports/pdf", params={"business_id": business.id, **period})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('attachment; filename="profitleak_')
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(response.content))
    return reader, "\n".join(page.extract_text() for page in reader.pages)


def test_pdf_contains_exact_kpis_signals_recommendations_and_sources(client, db):
    demo = load_demo(db)
    insights.run_analysis(db, demo.business.id, demo.period)
    db.commit()
    reader, text = read_pdf(client, demo.business)
    for expected in (
        "5 454 000,00 KZT",
        "2 475 000,00 KZT",
        "2 242 500,00 KZT",
        "Рост расходов",
        "Падение маржи",
        "Возможный дубликат",
        "16 500,00 KZT",
        "337 500,00 KZT",
        "Не оценена",
        "taraz-cafe-v1_expenses.csv",
        "не суммируются",
        "Что проверить",
        "Страница 1",
    ):
        assert expected in text
    assert len(reader.pages) >= 3
    assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 1
    read_pdf(client, demo.business)
    assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 1


def test_pdf_without_analysis_missing_cost_empty_and_literal_markup(client, db):
    demo = load_demo(db)
    db.get(Business, demo.business.id).name = "Кафе <Тест & партнёры>"
    sale = db.scalar(select(Sale).where(Sale.business_id == demo.business.id))
    sale.unit_cost = None
    db.commit()
    _, text = read_pdf(client, demo.business)
    assert "Кафе <Тест & партнёры>" in text
    assert "Недостаточно данных" in text
    assert "ещё не запускался" in text
    assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 0
    other = Business(name="Other empty", industry="retail")
    db.add(other)
    db.commit()
    _, text = read_pdf(client, other, date_from="2026-10-01", date_to="2026-10-01")
    assert "Other empty" in text and "5 454 000" not in text
    assert "отсутствуют" in text


def test_pdf_stale_snapshot_is_explicit_and_date_scope_is_respected(client, db):
    demo = load_demo(db)
    insights.run_analysis(db, demo.business.id, demo.period)
    confirm_import(
        db,
        demo.business.id,
        "expenses",
        parse_file(
            "new.csv",
            (
                "date,category,description,amount\n2026-10-01,Packaging,New purchase,100.00\n"
            ).encode(),
            "expenses",
        ),
    )
    db.commit()
    _, text = read_pdf(client, demo.business)
    assert "анализ устарел" in text
    _, short = read_pdf(client, demo.business, date_from="2026-10-01", date_to="2026-10-01")
    assert "5 454 000" not in short
    assert "Рост расходов" not in short
    assert "ещё не запускался" in short


def test_pdf_rejects_invalid_business_or_period(client):
    assert client.get("/api/v1/reports/pdf", params={"business_id": uuid4()}).status_code == 404
    assert client.get("/api/v1/reports/pdf", params={"business_id": "bad"}).status_code == 422
