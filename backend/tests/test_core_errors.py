from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode


def test_app_error_uses_unified_response(client: TestClient) -> None:
    @client.app.get("/api/test-error")
    def test_error() -> None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)

    response = client.get("/api/test-error")

    assert response.status_code == 404
    assert response.json() == {"code": 40401, "message": "任务不存在", "data": None}


def test_validation_error_uses_business_error_code(client: TestClient) -> None:
    @client.app.get("/api/needs-int")
    def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    response = client.get("/api/needs-int", params={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 40001
    assert body["message"] == "参数校验失败"
    assert body["data"]
