"""Tests for Model Router logic and API behavior."""
from fastapi.testclient import TestClient

from app.logic import LogicError, run
from app.main import app

SAMPLE = {'models': '[{"name":"fast-local","capability":62,"latency_ms":180,"cost_per_1k":0},{"name":"balanced-local","capability":78,"latency_ms":420,"cost_per_1k":0.2},{"name":"quality-cloud","capability":92,"latency_ms":900,"cost_per_1k":1.8}]',
 'task': 'coding',
 'max_latency_ms': 1200,
 'max_cost_per_1k': 2}


def test_sample_run():
    res = run(SAMPLE)
    assert res["summary"]
    assert isinstance(res["result"], dict)
    assert res['result']['metrics']['selected'] == 'balanced-local'


def test_empty_payload_is_rejected():
    try:
        run({})
    except LogicError:
        return
    raise AssertionError("empty payload should raise LogicError")


def test_health_and_meta():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    meta = client.get("/api/meta")
    assert meta.status_code == 200
    assert meta.json()["agent"] == "plotxyz-model-router-agent"


def test_run_endpoint_and_history():
    client = TestClient(app)
    response = client.post("/api/run", json={"payload": SAMPLE})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]
    assert body["task_id"] is not None
    history = client.get("/api/history?limit=5")
    assert history.status_code == 200
    assert len(history.json()["items"]) >= 1


def test_invalid_payload_returns_422():
    client = TestClient(app)
    response = client.post("/api/run", json={"payload": {}})
    assert response.status_code == 422


def test_payload_limit_returns_413():
    client = TestClient(app)
    response = client.post("/api/run", json={"payload": {"blob": "x" * 200001}})
    assert response.status_code == 413
