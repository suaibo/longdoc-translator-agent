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


def test_gradio_css_keeps_control_labels_and_selected_state_visible() -> None:
    from app.ui.gradio_app import CSS

    assert ".gradio-container label," in CSS
    assert 'label:has(input[type="radio"]:checked)' in CSS
    assert 'label:has(input[type="checkbox"]:checked)' in CSS
    assert "accent-color: var(--teal)" in CSS
