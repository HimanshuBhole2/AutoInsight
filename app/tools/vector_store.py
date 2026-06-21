"""
Vector store abstraction.

Backend selected by VECTOR_STORE_BACKEND env var:
  chroma     — local Chroma (dev default)
  databricks — Databricks Vector Search (prod)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.config import get_settings


class VectorStore(Protocol):
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        score_threshold: float = 0.72,
    ) -> list[str]: ...

    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None: ...


# ── Chroma backend (dev) ──────────────────────────────────────────────────────


class ChromaVectorStore:
    def __init__(self, persist_dir: str) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="autoinsight_knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        score_threshold: float = 0.72,
    ) -> list[str]:
        results = self._collection.query(
            query_texts=[query],
            n_results=k,
            include=["documents", "distances"],
        )
        docs = results["documents"][0] if results["documents"] else []
        distances = results["distances"][0] if results["distances"] else []

        # Chroma cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity: 1 - (dist / 2), keep above threshold
        filtered = [
            doc
            for doc, dist in zip(docs, distances, strict=False)
            if (1.0 - dist / 2.0) >= score_threshold
        ]
        return filtered

    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        import hashlib

        ids = [hashlib.md5(t.encode()).hexdigest() for t in texts]
        self._collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas or [{} for _ in texts],
        )


# ── Databricks backend (prod) ─────────────────────────────────────────────────


class DatabricksVectorStore:
    def __init__(self, host: str, token: str, index_name: str) -> None:
        # Lazy import — databricks-sdk is optional
        from databricks.vector_search.client import VectorSearchClient  # type: ignore[import]

        self._client = VectorSearchClient(host=host, token=token)
        self._index = self._client.get_index(index_name=index_name)

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        score_threshold: float = 0.72,
    ) -> list[str]:
        results = self._index.similarity_search(
            query_text=query,
            num_results=k,
            filters={},
        )
        return [
            r["page_content"]
            for r in results.get("result", {}).get("data_array", [])
            if r.get("score", 0) >= score_threshold
        ]

    def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        raise NotImplementedError("Use Delta Lake ingestion pipeline for Databricks VSS")


# ── Factory ───────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    settings = get_settings()
    if settings.vector_store_backend == "databricks":
        return DatabricksVectorStore(
            host=settings.databricks_host,
            token=settings.databricks_token,
            index_name=settings.databricks_vss_index,
        )
    return ChromaVectorStore(persist_dir=settings.chroma_persist_dir)
