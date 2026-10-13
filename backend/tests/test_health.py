from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def test_health_when_database_is_unavailable():
    class UnavailableDatabase:
        def execute(self, statement):
            raise OperationalError("SELECT 1", {}, Exception("sensitive connection information"))

    app.dependency_overrides[get_db] = lambda: UnavailableDatabase()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health")
        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
    finally:
        app.dependency_overrides.clear()
