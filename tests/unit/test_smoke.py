"""Smoke tests: FastAPI boots, GET / returns expected payload."""


def test_root_returns_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_health_endpoint(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_missing_api_key_returns_401(client):
    resp = client.post("/api/v1/jobs", json={"dataset_id": "abc", "query": "what is the trend?"})
    assert resp.status_code == 422 or resp.status_code == 401


def test_invalid_api_key_returns_401(client):
    resp = client.post(
        "/api/v1/jobs",
        json={"dataset_id": "abc", "query": "what is the trend?"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_create_job_stub(client, api_headers):
    resp = client.post(
        "/api/v1/jobs",
        json={"dataset_id": "abc", "query": "What are the top selling products?"},
        headers=api_headers,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"


def test_job_status_stub(client, api_headers):
    resp = client.get("/api/v1/jobs/some-job-id/status", headers=api_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "some-job-id"
    assert "status" in body


def test_list_reports(client, api_headers):
    resp = client.get("/api/v1/reports", headers=api_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "reports" in body
    assert isinstance(body["reports"], list)
