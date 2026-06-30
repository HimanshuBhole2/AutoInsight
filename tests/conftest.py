import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("VALID_API_KEYS", "test-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/autoinsight_test"
)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")


def _now() -> datetime:
    return datetime.now(tz=UTC)


@pytest.fixture
def mock_db():
    """AsyncSession mock — configure .get.return_value per test for specific DB state."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    _result = MagicMock()
    _result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def client(mock_db):
    from app.api.deps import get_db
    from app.main import app

    async def _override():
        yield mock_db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def api_headers():
    return {"X-API-Key": "test-key"}


# ── Helpers for seeding mock DB with model objects ─────────────────────────────


def make_dataset(**kwargs) -> object:
    from app.db.base import Dataset

    defaults: dict = dict(
        dataset_id="test-dataset-id",
        filename="test.csv",
        s3_path="data/uploads/test-dataset-id.csv",
        size_bytes=1024,
        row_count=100,
        col_count=5,
        status="READY",
        metadata_json={},
        created_at=_now(),
    )
    defaults.update(kwargs)
    return Dataset(**defaults)


def make_job(**kwargs) -> object:
    from app.db.base import Job

    now = _now()
    defaults: dict = dict(
        job_id="test-job-id",
        dataset_id="test-dataset-id",
        query="What are the top products by revenue?",
        config_json={},
        status="QUEUED",
        current_node=None,
        error_message=None,
        report_id=None,
        created_at=now,
        updated_at=now,
    )
    defaults.update(kwargs)
    return Job(**defaults)


def make_report(**kwargs) -> object:
    from app.db.base import Report

    defaults: dict = dict(
        report_id="test-report-id",
        job_id="test-job-id",
        dataset_id="test-dataset-id",
        s3_path="",
        quality_score=None,
        report_json={"insights": []},
        created_at=_now(),
    )
    defaults.update(kwargs)
    return Report(**defaults)
