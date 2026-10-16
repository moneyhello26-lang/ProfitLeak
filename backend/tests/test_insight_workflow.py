from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models import BusinessMembership, User
from app.services import auth

PASSWORD = "Correct horse battery 2026"


@pytest.fixture
def client(db):
    auth._attempts.clear()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        auth._attempts.clear()


def register(client, email):
    response = client.post("/api/v1/auth/register", json={
        "email": email, "password": PASSWORD, "full_name": "Workflow tester"
    })
    assert response.status_code == 201, response.text


@pytest.fixture
def signal(client):
    register(client, "workflow-owner@example.test")
    business_id = client.post("/api/v1/demo/load").json()["business"]["id"]
    assert client.post("/api/v1/analysis/run", json={"business_id": business_id}).status_code == 200
    items = client.get("/api/v1/insights", params={"business_id": business_id}).json()["items"]
    return business_id, items[0]


def endpoint(signal):
    business_id, item = signal
    return f"/api/v1/insights/{item['id']}/workflow?business_id={business_id}"


def test_review_survives_reanalysis_without_changing_evidence(client, signal):
    business_id, before = signal
    assert before["workflow_status"] == "new"
    for status in ("in_progress", "reviewed", "dismissed", "new"):
        response = client.patch(endpoint(signal), json={
            "status": status, "note": "  Проверили накладные. Тексерілді.  "
        })
        assert response.status_code == 200, response.text
        saved = response.json()
        assert saved["workflow_status"] == status
        assert saved["workflow_note"] == "Проверили накладные. Тексерілді."
        assert saved["workflow_updated_at"] is not None
    client.post("/api/v1/analysis/run", json={"business_id": business_id})
    after = client.get(f"/api/v1/insights/{before['id']}",
                       params={"business_id": business_id}).json()
    assert after["workflow_note"] == saved["workflow_note"]
    assert after["workflow_updated_at"] == saved["workflow_updated_at"]
    assert after["evidence"] == before["evidence"]
    assert after["potential_savings_kzt"] == before["potential_savings_kzt"]


def test_write_permissions_and_tenant_isolation(client, db, signal):
    business_id, item = signal
    register(client, "workflow-viewer@example.test")
    payload = {"status": "reviewed", "note": "checked"}
    assert client.patch(endpoint(signal), json=payload).status_code == 404
    user = db.scalar(select(User).where(User.email == "workflow-viewer@example.test"))
    membership = BusinessMembership(business_id=UUID(business_id), user_id=user.id, role="viewer")
    db.add(membership)
    db.commit()
    assert client.patch(endpoint(signal), json=payload).status_code == 403
    assert client.get(f"/api/v1/insights/{item['id']}",
                      params={"business_id": business_id}).json()["workflow_status"] == "new"
    membership.role = "analyst"
    db.commit()
    assert client.patch(endpoint(signal), json=payload).status_code == 200
    unknown = endpoint(signal).replace(item["id"], str(uuid4()))
    assert client.patch(unknown, json=payload).status_code == 404
    client.post("/api/v1/auth/logout")
    assert client.patch(endpoint(signal), json=payload).status_code == 401


def test_filter_by_review_status_combines_with_type_and_validates_enum(client, signal):
    business_id, item = signal
    params = {"business_id": business_id, "workflow_status": "in_progress"}
    assert client.get("/api/v1/insights", params=params).json()["total"] == 0
    client.patch(endpoint(signal), json={"status": "in_progress", "note": "check supplier"})
    result = client.get("/api/v1/insights", params=params).json()
    assert result["total"] == 1 and result["items"][0]["id"] == item["id"]
    result = client.get("/api/v1/insights", params={**params, "type": item["type"]}).json()
    assert result["total"] == 1
    assert client.get("/api/v1/insights", params={**params, "offset": 1}).json()["items"] == []
    invalid = client.get("/api/v1/insights", params={**params, "workflow_status": "done"})
    assert invalid.status_code == 422


@pytest.mark.parametrize("payload", [
    {"status": "done", "note": ""}, {"status": "new", "note": "x" * 2001},
    {"status": "reviewed"}, {"status": "reviewed", "note": "", "estimated_savings": "100"},
])
def test_invalid_updates_leave_signal_unchanged(client, signal, payload):
    assert client.patch(endpoint(signal), json=payload).status_code == 422
    business_id, item = signal
    saved = client.get(f"/api/v1/insights/{item['id']}",
                       params={"business_id": business_id}).json()
    assert saved["workflow_status"] == "new" and saved["workflow_note"] == ""
