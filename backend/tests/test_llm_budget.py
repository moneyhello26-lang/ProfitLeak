import json

import httpx
import pytest

from app.core.config import Settings
from app.schemas.advisor import AdvisorRequest
from app.services import advisor, insights, llm_budget
from app.services.demo import load_demo


@pytest.fixture(autouse=True)
def clear_state():
    llm_budget.clear()
    yield
    llm_budget.clear()


@pytest.fixture
def context(db):
    demo = load_demo(db)
    insights.run_analysis(db, demo.business.id, demo.period)
    return advisor.context(db, demo.business.id, demo.period)


def config(**values):
    return Settings(_env_file=None, llm_enabled=True, openai_api_key="test-openai", **values)


def request(ctx, **values):
    return AdvisorRequest(
        business_id=ctx.summary.business_id,
        message="Объясни выручку",
        allow_external=True,
        **values,
    )


def model_answer():
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {
                                "answer": "Выручка {{revenue}}. Проверьте расходы.",
                                "fact_ids": ["revenue"],
                            }
                        ),
                    }
                ],
            }
        ],
    }


def test_identical_question_is_cached_but_scope_facts_key_model_history_change_cache(
    context,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        advisor, "request_llm", lambda settings, payload: calls.append(payload) or model_answer()
    )
    settings = config()
    payload = request(context)
    first = advisor.respond(settings, payload, context)
    second = advisor.respond(settings, payload, context)
    assert first.cached is False and second.cached is True
    assert len(calls) == 1 and first.answer == second.answer
    payload = request(context, history=[{"role": "user", "content": "previous"}])
    advisor.respond(settings, payload, context)
    assert len(calls) == 2
    settings.llm_model = "gpt-4.1-mini"
    advisor.respond(settings, payload, context)
    assert len(calls) == 3
    from pydantic import SecretStr

    settings.openai_api_key = SecretStr("other-key")
    advisor.respond(settings, payload, context)
    assert len(calls) == 4
    context.facts[0].value = "1,00 KZT"
    reply = advisor.respond(settings, payload, context)
    assert len(calls) == 5 and "1,00 KZT" in reply.answer
    from uuid import uuid4

    payload.business_id = uuid4()
    advisor.respond(settings, payload, context)
    assert len(calls) == 6


def test_cache_expiry_and_disabled_cache(context, monkeypatch):
    moment = [100.0]
    monkeypatch.setattr(llm_budget.time, "monotonic", lambda: moment[0])
    calls = []
    monkeypatch.setattr(advisor, "request_llm", lambda *args: calls.append(1) or model_answer())
    settings = config(llm_cache_ttl_seconds=10)
    payload = request(context)
    advisor.respond(settings, payload, context)
    moment[0] += 11
    assert advisor.respond(settings, payload, context).cached is False
    settings.llm_cache_ttl_seconds = 0
    advisor.respond(settings, payload, context)
    advisor.respond(settings, payload, context)
    assert len(calls) == 4


@pytest.mark.parametrize(
    "code,expected,seconds",
    [
        ("insufficient_quota", "quota_exhausted", 900),
        ("organization_usage_limit_exceeded", "quota_exhausted", 900),
        ("rate_limit_exceeded", "rate_limit", 60),
    ],
)
def test_quota_pause_avoids_repeated_requests(context, monkeypatch, code, expected, seconds):
    moment = [100.0]
    monkeypatch.setattr(llm_budget.time, "monotonic", lambda: moment[0])
    original_client = httpx.Client
    calls = []

    def handle(req):
        calls.append(1)
        return httpx.Response(429, json={"error": {"code": code}})

    monkeypatch.setattr(
        advisor.httpx,
        "Client",
        lambda **kw: original_client(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    settings = config()
    payload = request(context)
    first = advisor.respond(settings, payload, context)
    second = advisor.respond(settings, payload, context)
    assert first.fallback_reason == second.fallback_reason == expected
    assert second.retry_after_seconds == seconds
    assert len(calls) == 1
    moment[0] += seconds + 1
    advisor.respond(settings, payload, context)
    assert len(calls) == 2


def test_cached_answers_require_consent_even_when_quota_paused(context, monkeypatch):
    calls = []

    def provider(*args):
        calls.append(1)
        return model_answer()

    monkeypatch.setattr(advisor, "request_llm", provider)
    settings = config()
    payload = request(context)
    advisor.respond(settings, payload, context)
    llm_budget.pause(settings, "quota_exhausted", 900)
    assert advisor.respond(settings, payload, context).cached is True
    payload.allow_external = False
    assert advisor.respond(settings, payload, context).fallback_reason == "consent_required"
    assert len(calls) == 1


def test_history_and_context_are_reduced(context, monkeypatch):
    seen = []
    monkeypatch.setattr(
        advisor, "request_llm", lambda settings, payload: seen.append(payload) or model_answer()
    )
    payload = request(context, history=[{"role": "user", "content": "x" * 6000}] * 8)
    advisor.respond(config(), payload, context)
    assert len(seen[0]["input"]) == 6
    assert all(len(item["content"]) == 1200 for item in seen[0]["input"][1:-1])
    assert seen[0]["max_output_tokens"] == 600
    assert len(json.loads(seen[0]["input"][0]["content"].split(": ", 1)[1])["signals"]) <= 3
    seen.clear()
    advisor.respond(config(llm_history_messages=0), payload, context)
    assert len(seen[0]["input"]) == 2


def test_gemini_protocol_key_and_explicit_consent(context, monkeypatch):
    settings = config(llm_provider="gemini", gemini_api_key="test-gemini")
    payload = request(context)
    original_client = httpx.Client
    calls = []

    def handle(req):
        calls.append(1)
        assert str(req.url).endswith("/gemini-3.5-flash-lite:generateContent")
        assert req.headers["x-goog-api-key"] == "test-gemini"
        assert "Authorization" not in req.headers and "test-openai" not in req.content.decode()
        body = json.loads(req.content)
        assert body["generationConfig"]["maxOutputTokens"] == 600
        assert body["generationConfig"]["responseFormat"]["text"]["mimeType"] == "APPLICATION_JSON"
        assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"
        assert body["systemInstruction"]["parts"][0]["text"] == advisor.INSTRUCTIONS
        raw = model_answer()["output"][0]["content"][0]["text"]
        return httpx.Response(
            200,
            json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": raw}]}}]},
        )

    monkeypatch.setattr(
        advisor.httpx,
        "Client",
        lambda **kw: original_client(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    assert advisor.respond(settings, payload, context).fallback_reason == "consent_required"
    assert calls == []
    payload.external_provider = "openai"
    assert advisor.respond(settings, payload, context).fallback_reason == "consent_required"
    payload.external_provider = "gemini"
    reply = advisor.respond(settings, payload, context)
    assert reply.provider == "gemini" and reply.source == "llm"
    assert "5 454 000,00 KZT" in reply.answer
    assert len(calls) == 1


def test_gemini_missing_key_never_uses_openai_key(context, monkeypatch):
    monkeypatch.setattr(advisor, "request_llm", lambda *args: pytest.fail("network"))
    reply = advisor.respond(config(llm_provider="gemini"), request(context), context)
    assert reply.fallback_reason == "missing_key"


def test_invalid_answer_is_not_cached(context, monkeypatch):
    calls = []
    monkeypatch.setattr(advisor, "request_llm", lambda *args: calls.append(1) or {})
    settings = config()
    for _ in range(2):
        assert advisor.respond(settings, request(context), context).source == "template"
    assert len(calls) == 2
