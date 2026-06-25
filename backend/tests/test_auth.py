from fastapi.testclient import TestClient


def test_auth_login_logout_and_me(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"username": "testuser", "password": "test-password"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "testuser"

    logout = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert logout.status_code == 200
    expired = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert expired.status_code == 401


def test_jobs_require_login_and_are_user_scoped(client: TestClient) -> None:
    unauthenticated = client.get("/api/jobs", headers={"Authorization": ""})
    assert unauthenticated.status_code == 401

    created = client.post(
        "/api/jobs",
        files={"file": ("paper.md", b"# Paper", "text/markdown")},
        data={"targetLanguage": "ja"},
    )
    assert created.status_code == 200
    job_id = created.json()["data"]["jobId"]

    second = client.post(
        "/api/auth/register",
        json={"username": "second-user", "password": "second-password"},
    )
    second_token = second.json()["data"]["token"]
    hidden = client.get(
        f"/api/jobs/{job_id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert hidden.status_code == 404

    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["targetLanguage"] == "ja"
