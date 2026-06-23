from fastapi.testclient import TestClient

from app.core.errors import AppError, ErrorCode
from app.main import create_app


def test_app_error_uses_unified_response() -> None:
    test_app = create_app()

    @test_app.get("/api/test-error")
    def test_error() -> None:
        raise AppError(ErrorCode.JOB_NOT_FOUND, status_code=404)

    with TestClient(test_app) as client:
        response = client.get("/api/test-error")

    assert response.status_code == 404
    assert response.json() == {"code": 40401, "message": "任务不存在", "data": None}


def test_validation_error_uses_business_error_code() -> None:
    test_app = create_app()

    @test_app.get("/api/needs-int")
    def needs_int(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(test_app) as client:
        response = client.get("/api/needs-int", params={"value": "not-an-int"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 40001
    assert body["message"] == "参数校验失败"
    assert body["data"]
