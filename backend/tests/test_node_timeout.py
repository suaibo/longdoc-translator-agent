import time

import pytest

from app.agent.graph import _instrument_node
from app.core.config import get_settings
from app.core.errors import AppError


def test_node_time_budget_marks_slow_node_failed(monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_NODE_TIMEOUT_SECONDS", "0.001")
    monkeypatch.setattr("app.agent.graph._record_event", lambda *args, **kwargs: None)
    get_settings.cache_clear()

    def slow_node(_state):
        time.sleep(0.01)
        return {}

    try:
        wrapped = _instrument_node("slow_node", slow_node)
        with pytest.raises(AppError) as error:
            wrapped({"job_id": "job_timeout"})
    finally:
        get_settings.cache_clear()

    assert error.value.status_code == 504
