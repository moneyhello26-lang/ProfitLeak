from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db, make_engine
from app.main import app
from app.models import AccountBootstrap, Business, BusinessMembership, User, UserSession
from app.schemas.auth import RegisterRequest
from app.services import auth

PASSWORD = "Correct horse battery 2026"
pytestmark = pytest.mark.integration


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


def register(client, email="owner@example.test"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": "Тест қолданушы",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def business(client):
    response = client.post("/api/v1/businesses", json={"name": "Кафе", "industry": "cafe"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "/auth/me",
        "/businesses",
        "/imports",
        "/dashboard/summary",
        "/analytics/revenue",
        "/analytics/products",
        "/analytics/expenses",
        "/analytics/comparison",
        "/analytics/forecast",
        "/insights",
        "/reports/pdf",
        "/advisor/status",
    ],
)
def test_unauthenticated_read_is_denied(client, endpoint):
    response = client.get("/api/v1" + endpoint, params={"business_id": str(uuid4())})
    assert response.status_code == 401, response.text
    assert response.json()["detail"]["code"] == "authentication_required"


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("/businesses", {"name": "Unauthorized", "industry": "cafe"}),
        ("/demo/load", {}),
        ("/analysis/run", {"business_id": str(uuid4())}),
        ("/advisor/chat", {"business_id": str(uuid4()), "message": "Итог"}),
    ],
)
def test_unauthenticated_mutation_is_denied(client, endpoint, payload):
    response = client.post("/api/v1" + endpoint, json=payload)
    assert response.status_code == 401


def test_anonymous_health_is_public(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_registration_session_hash_and_logout(client, db):
    result = register(client, "  OWNER@EXAMPLE.TEST  ")
    assert result["user"]["email"] == "owner@example.test"
    assert result["memberships"] == []
    cookie = client.cookies.get(auth.COOKIE_NAME)
    row = db.scalar(select(UserSession))
    assert row.token_hash != cookie
    assert row.token_hash == auth.token_digest(cookie)
    user = db.scalar(select(User))
    assert user.password_hash.startswith("scrypt$")
    assert PASSWORD not in user.password_hash
    assert client.get("/api/v1/auth/me").json() == result
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    client.cookies.set(auth.COOKIE_NAME, cookie)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0


def test_cookie_flags_password_and_no_sensitive_response(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "owner@example.test",
            "password": PASSWORD,
            "full_name": "Owner",
        },
    )
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/api/v1" in header
    assert response.headers["cache-control"] == "no-store"
    assert "password" not in response.text and "token" not in response.text
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "bad",
                "password": "short",
                "full_name": "",
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("locale", ["ru", "kk"])
def test_invalid_password_is_never_echoed_in_validation(client, locale):
    secret = "secret-with-invalid-length-" * 8
    response = client.post(
        "/api/v1/auth/register",
        headers={"Accept-Language": locale},
        json={
            "email": "owner@example.test",
            "password": secret,
            "full_name": "Owner",
        },
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert all("input" not in issue for issue in response.json()["detail"])
    assert response.json()["detail"][0]["ctx"] == {"max_length": 128}


def test_first_registration_claims_existing_business_once(client, db):
    previous = Business(name="Existing local business", industry="cafe")
    db.add(previous)
    db.flush()
    first = register(client)
    assert first["memberships"] == [{"business_id": str(previous.id), "role": "owner"}]
    assert db.get(AccountBootstrap, 1).claimed_by == UUID(first["user"]["id"])
    client.post("/api/v1/auth/logout")
    # Even a later unowned record cannot be adopted by a second registration.
    later = Business(name="Later unowned business", industry="cafe")
    db.add(later)
    db.flush()
    second = register(client, "other@example.test")
    assert second["memberships"] == []
    assert client.get("/api/v1/businesses").json() == []
    assert (
        client.get(
            "/api/v1/dashboard/summary", params={"business_id": str(previous.id)}
        ).status_code
        == 404
    )


def test_login_errors_duplicate_email_and_rate_limit(client):
    register(client)
    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "OWNER@example.test",
            "password": PASSWORD,
            "full_name": "Other",
        },
    )
    assert duplicate.status_code == 409
    client.post("/api/v1/auth/logout")
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.test",
                "password": "wrong-password",
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_credentials"
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.test",
                "password": PASSWORD,
            },
        ).status_code
        == 429
    )


def test_expiry_rotation_and_password_revoke_all_sessions(client, db):
    register(client)
    original = client.cookies.get(auth.COOKIE_NAME)
    login(client, "owner@example.test")
    rotated = client.cookies.get(auth.COOKIE_NAME)
    assert rotated != original
    assert (
        db.scalar(select(UserSession).where(UserSession.token_hash == auth.token_digest(original)))
        is None
    )
    session = db.scalar(select(UserSession))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401
    login(client, "owner@example.test")
    live = client.cookies.get(auth.COOKIE_NAME)
    assert (
        client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "wrong",
                "new_password": "New password 2027",
            },
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": "New password 2027",
            },
        ).status_code
        == 204
    )
    client.cookies.set(auth.COOKIE_NAME, live)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert db.scalar(select(func.count()).select_from(UserSession)) == 0
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.test",
                "password": "New password 2027",
            },
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://localhost:5173.evil.example"]
)
def test_cross_origin_mutations_are_rejected(client, origin):
    response = client.post(
        "/api/v1/auth/register",
        headers={"Origin": origin},
        json={
            "email": "owner@example.test",
            "password": PASSWORD,
            "full_name": "Owner",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_origin"


def test_csrf_fetch_metadata_and_allowed_origin(client):
    response = client.post(
        "/api/v1/auth/login",
        headers={"Sec-Fetch-Site": "cross-site"},
        json={
            "email": "owner@example.test",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 403
    response = client.post(
        "/api/v1/auth/register",
        headers={"Origin": "http://127.0.0.1:5173"},
        json={
            "email": "owner@example.test",
            "password": PASSWORD,
            "full_name": "Owner",
        },
    )
    assert response.status_code == 201
    assert response.headers["access-control-allow-credentials"] == "true"


def test_roles_membership_changes_and_last_owner(client, db):
    owner = register(client)
    id_ = business(client)
    root = f"/api/v1/businesses/{id_}/members"
    client.post("/api/v1/auth/logout")
    analyst = register(client, "analyst@example.test")
    client.post("/api/v1/auth/logout")
    viewer = register(client, "viewer@example.test")
    client.post("/api/v1/auth/logout")
    login(client, "owner@example.test")
    for email, role in [(analyst["user"]["email"], "analyst"), (viewer["user"]["email"], "viewer")]:
        assert client.post(root, json={"email": email, "role": role}).status_code == 201
    assert len(client.get(root).json()) == 3
    assert (
        client.post(root, json={"email": "missing@example.test", "role": "viewer"}).status_code
        == 404
    )
    assert (
        client.post(root, json={"email": "viewer@example.test", "role": "viewer"}).status_code
        == 409
    )
    assert client.patch(f"{root}/{owner['user']['id']}", json={"role": "viewer"}).status_code == 409
    assert client.delete(f"{root}/{owner['user']['id']}").status_code == 409
    client.post("/api/v1/auth/logout")
    login(client, "viewer@example.test")
    assert client.get("/api/v1/businesses").json()[0]["id"] == id_
    for endpoint in [
        "/dashboard/summary",
        "/analytics/forecast",
        "/analytics/comparison",
        "/imports",
        "/insights",
    ]:
        assert client.get("/api/v1" + endpoint, params={"business_id": id_}).status_code == 200
    assert client.get("/api/v1/reports/pdf", params={"business_id": id_}).status_code == 200
    assert (
        client.post(
            "/api/v1/advisor/chat", json={"business_id": id_, "message": "Итог"}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/analysis/run", json={"business_id": id_}).status_code == 403
    assert client.get(root).status_code == 403
    for endpoint in ["preview", "confirm"]:
        response = client.post(
            f"/api/v1/imports/{endpoint}",
            data={
                "business_id": id_,
                "kind": "expenses",
                "preview_token": "not-a-token",
            },
            files={
                "file": (
                    "expenses.csv",
                    b"date,category,description,amount\n2026-10-01,Rent,Rent,10\n",
                )
            },
        )
        assert response.status_code == 403
    client.post("/api/v1/auth/logout")
    login(client, "analyst@example.test")
    assert client.post("/api/v1/analysis/run", json={"business_id": id_}).status_code == 200
    assert client.get(root).status_code == 403
    preview = client.post(
        "/api/v1/imports/preview",
        data={"business_id": id_, "kind": "expenses"},
        files={
            "file": ("expenses.csv", b"date,category,description,amount\n2026-10-01,Rent,Rent,10\n")
        },
    )
    assert preview.status_code == 200 and preview.json()["can_confirm"]
    client.post("/api/v1/auth/logout")
    login(client, "owner@example.test")
    assert client.patch(f"{root}/{viewer['user']['id']}", json={"role": "owner"}).status_code == 200
    assert client.patch(f"{root}/{owner['user']['id']}", json={"role": "viewer"}).status_code == 200
    # The changed role takes effect on the very next request, with the same session.
    assert client.get(root).status_code == 403
    client.post("/api/v1/auth/logout")
    login(client, "viewer@example.test")
    assert client.delete(f"{root}/{analyst['user']['id']}").status_code == 204
    client.post("/api/v1/auth/logout")
    login(client, "analyst@example.test")
    assert client.get("/api/v1/dashboard/summary", params={"business_id": id_}).status_code == 404


def test_personal_demo_and_tenant_isolation(client):
    register(client)
    first = client.post("/api/v1/demo/load").json()
    first_id = first["business"]["id"]
    assert client.post("/api/v1/demo/load").json()["already_loaded"] is True
    client.post("/api/v1/auth/logout")
    register(client, "other@example.test")
    assert client.get("/api/v1/businesses").json() == []
    second = client.post("/api/v1/demo/load").json()
    assert second["business"]["id"] != first_id
    assert second["already_loaded"] is False
    for endpoint in [
        "/dashboard/summary",
        "/analytics/forecast",
        "/analytics/comparison",
        "/reports/pdf",
        "/imports",
    ]:
        assert client.get("/api/v1" + endpoint, params={"business_id": first_id}).status_code == 404
    assert (
        client.post(
            "/api/v1/advisor/chat", json={"business_id": first_id, "message": "Итог"}
        ).status_code
        == 404
    )
    assert client.post("/api/v1/analysis/run", json={"business_id": first_id}).status_code == 404


def test_two_registrations_atomically_claim_only_one_owner(tmp_path):
    path = tmp_path / "bootstrap-race.db"
    engine = make_engine("sqlite:///" + path.as_posix())
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with Session(engine) as session:
        existing = Business(name="Pre-account data", industry="cafe")
        session.add(existing)
        session.commit()
        id_ = existing.id
    barrier = Barrier(2)

    def signup(index):
        barrier.wait(timeout=10)
        with Session(engine) as session:
            session.connection(execution_options={"sqlite_write": True})
            user = auth.register(
                session,
                RegisterRequest(
                    email=f"user{index}@example.test", password=PASSWORD, full_name="User"
                ),
            )
            session.commit()
            return user.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        users = list(executor.map(signup, [1, 2]))
    with Session(engine) as session:
        memberships = session.scalars(
            select(BusinessMembership).where(BusinessMembership.business_id == id_)
        ).all()
        assert len(memberships) == 1 and memberships[0].role == "owner"
        assert memberships[0].user_id in users
        assert session.get(AccountBootstrap, 1).claimed_by == memberships[0].user_id
    engine.dispose()
