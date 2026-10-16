import asyncio
import copy
import json
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.core.i18n import (
    LanguageMiddleware,
    get_language,
    language,
    localize_payload,
    select_language,
    translate,
)
from app.db.session import get_db
from app.main import app
from app.models import Insight
from app.services import advisor, insights, llm_budget
from app.services.demo import load_demo


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("", "ru"),
        ("kk", "kk"),
        ("kk-KZ,ru;q=0.8", "kk"),
        ("kk;q=0.5,ru;q=0.9", "ru"),
        ("kk;q=0,ru;q=0.5", "ru"),
        ("en-US,en;q=0.9", "ru"),
        ("en-US,kk;q=0.5", "kk"),
        ("kk;q=invalid", "ru"),
        ("kk;q=NaN", "ru"),
    ],
)
def test_language_negotiation(header, expected):
    assert select_language(header) == expected


def test_translation_preserves_import_contract_and_user_text():
    payload = {
        "name": "Выручка",
        "category": "Выручка",
        "filename": "Расходы по категориям.csv",
        "title": "Падение маржи: Выручка",
        "current_value": "1234.50",
        "type": "MARGIN_DROP",
        "recommendation": (
            "Сценарные оценки не суммируются и не являются гарантированной экономией."
        ),
        "errors": [{"field": "product_name", "message": "Отсутствует обязательная колонка."}],
    }
    original = copy.deepcopy(payload)
    token = language.set("kk")
    try:
        result = localize_payload(payload)
        assert result["title"] == "Маржаның төмендеуі: Выручка"
        assert result["errors"][0] == {"field": "product_name", "message": "Міндетті баған жоқ."}
        for key in ("name", "category", "filename", "current_value", "type"):
            assert result[key] == payload[key]
        assert localize_payload(result) == result
    finally:
        language.reset(token)
    assert payload == original
    assert translate("Выручка") == "Выручка"


def test_concurrent_requests_keep_their_own_language_and_reset_context():
    async def endpoint(scope, receive, send):
        before = get_language()
        await asyncio.sleep(0)
        assert get_language() == before
        payload = json.dumps({"name": "Выручка", "message": "Войдите в аккаунт."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        # Streaming chunks must still become a valid localized JSON response.
        await send({"type": "http.response.body", "body": payload[:10], "more_body": True})
        await send({"type": "http.response.body", "body": payload[10:]})

    middleware = LanguageMiddleware(endpoint)

    async def request(locale):
        sent = []

        async def send(message):
            sent.append(message)

        async def receive():
            return {"type": "http.request", "body": b""}

        await middleware(
            {"type": "http", "headers": [(b"accept-language", locale.encode())]}, receive, send
        )
        body = b"".join(item.get("body", b"") for item in sent)
        assert json.loads(body)["message"] == (
            "Аккаунтқа кіріңіз." if locale == "kk" else "Войдите в аккаунт."
        )
        assert json.loads(body)["name"] == "Выручка"
        assert dict(sent[0]["headers"])[b"content-language"] == locale.encode()
        if locale == "kk":
            assert int(dict(sent[0]["headers"])[b"content-length"]) == len(body)

    async def exercise():
        await asyncio.gather(request("ru"), request("kk"), request("ru"), request("kk"))

    asyncio.run(exercise())
    assert get_language() == "ru"


@pytest.fixture
def localized_client(db):
    demo = load_demo(db)
    insights.run_analysis(db, demo.business.id, demo.period)
    db.commit()
    configuration = Settings(_env_file=None, llm_enabled=False)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = lambda: configuration
    llm_budget.clear()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"locale-{uuid4().hex}@example.test",
                    "password": "localization-test-123",
                    "full_name": "Қазақша тест",
                },
            )
            assert response.status_code == 201
            yield client, demo, configuration
    finally:
        app.dependency_overrides.clear()
        llm_budget.clear()


def test_kazakh_auth_import_and_validation_errors(localized_client):
    client, demo, _ = localized_client
    headers = {"Accept-Language": "kk-KZ"}
    missing = client.get(
        "/api/v1/dashboard/summary", params={"business_id": str(uuid4())}, headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["message"] == "Бизнес табылмады."
    preview = client.post(
        "/api/v1/imports/preview",
        headers=headers,
        data={"business_id": str(demo.business.id), "kind": "expenses"},
        files={"file": ("проверка.csv", b"date,amount\n2026-10-01,25\n", "text/csv")},
    )
    assert preview.status_code == 200
    assert preview.json()["filename"] == "проверка.csv"
    assert preview.json()["errors"][0] == {
        "row": 1,
        "field": "category",
        "message": "Міндетті баған жоқ.",
    }
    invalid = client.get(
        "/api/v1/analytics/forecast",
        params={"business_id": str(demo.business.id), "horizon_days": 100},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["msg"] == "Мән 90 санынан аспауы керек."
    client.post("/api/v1/auth/logout")
    denied = client.get("/api/v1/businesses", headers=headers)
    assert denied.status_code == 401
    assert denied.json()["detail"]["message"] == "Аккаунтқа кіріңіз."
    fallback = client.get("/api/v1/businesses", headers={"Accept-Language": "en"})
    assert fallback.json()["detail"]["message"] == "Войдите в аккаунт."


def test_saved_insights_translate_without_rewriting_canonical_evidence(localized_client, db):
    client, demo, _ = localized_client
    record = db.scalar(select(Insight).where(Insight.type == "MARGIN_DROP"))
    stored = copy.deepcopy(record.evidence_json)
    params = {"business_id": str(demo.business.id)}
    russian = client.get(f"/api/v1/insights/{record.id}", params=params).json()
    kazakh = client.get(
        f"/api/v1/insights/{record.id}", params=params, headers={"Accept-Language": "kk"}
    ).json()
    assert russian["evidence"]["title"].startswith("Падение маржи:")
    assert kazakh["evidence"]["title"].startswith("Маржаның төмендеуі:")
    assert kazakh["evidence"]["explanation"].startswith("Тауардың жалпы пайда")
    assert kazakh["recommendation"].startswith("Сатып алу бағасын")
    for field in ("entity", "current_value", "baseline_value", "source_rows", "product_id"):
        assert kazakh["evidence"][field] == russian["evidence"][field]
    analysis = client.post("/api/v1/analysis/run", json=params, headers={"Accept-Language": "kk"})
    assert analysis.status_code == 200
    assert analysis.json()["checks"][0]["reason"].startswith("Өсу шегі 25%")
    db.expire_all()
    assert db.get(Insight, record.id).evidence_json == stored


def test_planning_text_translates_but_forecasts_and_comparisons_do_not_change(localized_client):
    client, demo, _ = localized_client
    params = {"business_id": str(demo.business.id), "horizon_days": 60}
    for path in ("forecast", "comparison"):
        russian = client.get(f"/api/v1/analytics/{path}", params=params).json()
        response = client.get(
            f"/api/v1/analytics/{path}", params=params, headers={"Accept-Language": "kk"}
        )
        assert response.status_code == 200
        kazakh = response.json()
        assert response.headers["content-language"] == "kk"
        if path == "forecast":
            assert kazakh["assumptions"][0].startswith("Түсім мен өзіндік құн:")
            assert kazakh["warnings"][0].startswith("Болжам көкжиегі")
            assert kazakh["totals"] == russian["totals"]
        else:
            assert kazakh["products"] == russian["products"]
            assert kazakh["metrics"] == russian["metrics"]
        assert kazakh["points"] == russian["points"]


def test_kazakh_advisor_template_uses_saved_evidence_without_provider(
    localized_client, monkeypatch
):
    client, demo, _ = localized_client
    monkeypatch.setattr(
        advisor, "request_llm", lambda *args: pytest.fail("Unexpected provider call")
    )
    response = client.post(
        "/api/v1/advisor/chat",
        headers={"Accept-Language": "kk"},
        json={"business_id": str(demo.business.id), "message": "Маржа неге төмендеді?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "template"
    assert payload["answer"].startswith("Таңдалған кезеңнің көрсеткіштері:")
    assert "Маржаның төмендеуі" in payload["answer"]
    assert "Сатып алу бағасын" in payload["answer"]
    assert payload["facts"][0]["label"] == "Түсім"
    assert payload["facts"][0]["value"] == "5 454 000,00 KZT"
    assert payload["disclaimer"].startswith("Сигналдар мен сценарийлік")


def test_advisor_cache_is_separate_for_each_language(localized_client, monkeypatch):
    from pydantic import SecretStr

    client, demo, configuration = localized_client
    configuration.llm_enabled = True
    configuration.openai_api_key = SecretStr("localization-provider-test")
    seen = []

    def provider(settings, payload):
        seen.append(payload)
        locale = get_language()
        answer = "Түсім: {{revenue}}." if locale == "kk" else "Выручка: {{revenue}}."
        return {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps({"answer": answer, "fact_ids": ["revenue"]}),
                        }
                    ],
                }
            ],
        }

    monkeypatch.setattr(advisor, "request_llm", provider)
    for locale, cached in (("ru", False), ("kk", False), ("ru", True), ("kk", True)):
        response = client.post(
            "/api/v1/advisor/chat",
            headers={"Accept-Language": locale},
            json={
                "business_id": str(demo.business.id),
                "message": "Summary?",
                "allow_external": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["cached"] is cached
        assert response.json()["answer"].startswith("Түсім:" if locale == "kk" else "Выручка:")
    assert len(seen) == 2
    assert "қазақ тілінде" in seen[1]["instructions"]
    assert '"language":"kk"' in seen[1]["input"][0]["content"]


def test_kazakh_pdf_contains_glyphs_labels_exact_figures_and_literal_user_names(
    localized_client, db
):
    from app.models import Business
    from app.services.reports import FONT, pdfmetrics

    client, demo, _ = localized_client
    db.get(Business, demo.business.id).name = "Выручка <Ә Ғ Қ Ң Ө Ұ Ү Һ І>"
    db.commit()
    response = client.get(
        "/api/v1/reports/pdf",
        params={"business_id": str(demo.business.id)},
        headers={"Accept-Language": "kk"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    reader = PdfReader(BytesIO(response.content))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for phrase in (
        "Қаржылық есеп",
        "Выручка <Ә Ғ Қ Ң Ө Ұ Ү Һ І>",
        "Түсім",
        "Маржаның төмендеуі",
        "Шығындардың өсуі",
        "Нені тексеру керек",
        "Дереккөздер",
        "1-бет",
        "5 454 000,00 KZT",
        "taraz-cafe-v1_expenses.csv",
    ):
        assert phrase in text
    assert reader.metadata.title == "ProfitLeak AI - Қаржылық есеп"
    font = pdfmetrics.getFont(FONT)
    assert all(ord(letter) in font.face.charToGlyph for letter in "ӘәҒғҚқҢңӨөҰұҮүҺһІі")
