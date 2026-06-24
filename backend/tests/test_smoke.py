from fastapi.testclient import TestClient


def test_health_smoke(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": {
            "status": "UP",
            "service": "longdoc-translator-agent",
        },
    }
