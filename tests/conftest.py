import os

import pytest
from fastapi.testclient import TestClient

# Point at a test .env so real API keys aren't needed
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("VALID_API_KEYS", "test-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/autoinsight_test"
)
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def api_headers():
    return {"X-API-Key": "test-key"}
