from fastapi.testclient import TestClient

from app.main import app


def test_health_smoke() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "UP"
