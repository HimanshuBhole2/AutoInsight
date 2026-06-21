from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0"
    secret_key: str = "change-me-in-production"
    valid_api_keys: str = "dev-key-1"  # comma-separated

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/autoinsight"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # LLM
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # AWS / S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    s3_bucket: str = "autoinsight-dev"

    # Observability
    langchain_tracing_v2: str = "false"
    langchain_api_key: str = ""
    langchain_project: str = "autoinsight-dev"
    mlflow_tracking_uri: str = "http://localhost:5000"

    # Vector store
    vector_store_backend: Literal["chroma", "databricks"] = "chroma"
    chroma_persist_dir: str = "./chroma_db"
    databricks_host: str = ""
    databricks_token: str = ""
    databricks_vss_index: str = "autoinsight_knowledge_base"

    # Sandbox
    sandbox_timeout_seconds: int = 30
    sandbox_max_memory_mb: int = 512

    @property
    def api_keys(self) -> list[str]:
        return [k.strip() for k in self.valid_api_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
