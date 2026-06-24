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


def test_gradio_is_mounted(client: TestClient) -> None:
    response = client.get("/ui/")

    assert response.status_code == 200
    assert "LongDoc Translator Agent" in response.text
