"""Smoke tests: FastAPI boots, all routes respond correctly."""

from unittest.mock import MagicMock, patch

from tests.conftest import make_dataset, make_job, make_report


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
    assert resp.status_code in (422, 401)


def test_invalid_api_key_returns_401(client):
    resp = client.post(
        "/api/v1/jobs",
        json={"dataset_id": "abc", "query": "what is the trend?"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_create_job_returns_404_for_missing_dataset(client, api_headers):
    # mock_db.get returns None by default → dataset not found
    resp = client.post(
        "/api/v1/jobs",
        json={"dataset_id": "nonexistent", "query": "What are the top selling products?"},
        headers=api_headers,
    )
    assert resp.status_code == 404


def test_create_job_returns_queued(client, mock_db, api_headers):
    mock_db.get.return_value = make_dataset()

    with patch("app.workers.pipeline_task.run_agent_pipeline") as mock_task:
        mock_task.apply_async = MagicMock()
        resp = client.post(
            "/api/v1/jobs",
            json={"dataset_id": "test-dataset-id", "query": "What are the top selling products?"},
            headers=api_headers,
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body
    assert body["status"] == "QUEUED"


def test_job_status_returns_404_for_missing_job(client, api_headers):
    resp = client.get("/api/v1/jobs/nonexistent/status", headers=api_headers)
    assert resp.status_code == 404


def test_job_status_returns_queued(client, mock_db, api_headers):
    mock_db.get.return_value = make_job()

    resp = client.get("/api/v1/jobs/test-job-id/status", headers=api_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "test-job-id"
    assert body["status"] == "QUEUED"


def test_list_reports_returns_empty(client, api_headers):
    resp = client.get("/api/v1/reports", headers=api_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "reports" in body
    assert isinstance(body["reports"], list)
    assert body["total"] == 0


def test_get_report_returns_404_for_missing(client, api_headers):
    resp = client.get("/api/v1/reports/nonexistent", headers=api_headers)
    assert resp.status_code == 404


def test_get_report_returns_data(client, mock_db, api_headers):
    mock_db.get.return_value = make_report()

    resp = client.get("/api/v1/reports/test-report-id", headers=api_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"] == "test-report-id"
    assert "report" in body
