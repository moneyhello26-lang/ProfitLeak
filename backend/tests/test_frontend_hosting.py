import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.frontend import mount_frontend


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index.html").write_text("<html>ProfitLeak shell</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
    app = FastAPI()

    @app.get("/api/v1/probe")
    def probe():
        return {"status": "ok"}

    mount_frontend(app, tmp_path)
    with TestClient(app) as client:
        yield client


def test_direct_spa_links_and_assets(client):
    for path in ("/", "/insights", "/account/team"):
        response = client.get(path)
        assert response.status_code == 200
        assert "ProfitLeak shell" in response.text
        assert response.headers["cache-control"] == "no-cache"
    assert client.head("/insights").status_code == 200
    assert client.get("/assets/app.js").text == "console.log('app')"
    assert client.get("/api/v1/probe").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/v1/missing", "/api", "/assets/missing.js",
                                 "/assets/missing", "/templates/missing.csv", "/.env"])
def test_missing_api_and_files_do_not_return_spa(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "ProfitLeak shell" not in response.text


def test_only_read_methods_can_serve_shell(client):
    assert client.post("/insights").status_code == 405


def test_missing_build_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        mount_frontend(FastAPI(), tmp_path)


def test_disabled_frontend_leaves_api_only():
    app = FastAPI()
    mount_frontend(app, None)
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
