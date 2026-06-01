"""
database/milvus_client.py
--------------------------
Milvus connection, schema management, circuit breaker, search executors.
This module is imported first by database/__init__.py so that the
MilvusClient monkeypatch runs before any ORM-style Collection is used.
"""

import concurrent.futures
import logging
import os
import threading
import time
from typing import Optional

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_ollama import OllamaEmbeddings
from pymilvus import (
    CollectionSchema, DataType, FieldSchema, MilvusClient, connections
)

from database.config import (
    COLLECTION_NAME, MILVUS_CIRCUIT_BREAKER_SECONDS,
    MILVUS_HEALTHCHECK_TIMEOUT_SECONDS, MILVUS_INIT_TIMEOUT_SECONDS,
    MILVUS_TIMEOUT_SECONDS, OLLAMA_BASE_URL,
    _get_cloud_config, _get_local_config, _get_milvus_config,
)
from database.metadata import _filter_docs_by_sources, _milvus_source_filter_expr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MilvusClient monkeypatch — MUST run before any ORM Collection is created
# ---------------------------------------------------------------------------

_original_milvus_client_init = MilvusClient.__init__


def _patched_milvus_client_init(self, *args, **kwargs):
    _original_milvus_client_init(self, *args, **kwargs)
    connections._alias_handlers[self._using] = self._handler
    connections._alias_config[self._using] = {"db_name": kwargs.get("db_name", "")}


MilvusClient.__init__ = _patched_milvus_client_init

# Force Milvus into synchronous mode to avoid GRPC thread-safety issues.
os.environ["MILVUS_ASYNC"] = "0"

# ---------------------------------------------------------------------------
# Global health / circuit breaker state
# ---------------------------------------------------------------------------

_milvus_health = {
    "unhealthy_until": 0.0,
    "last_error": None,
}
_vector_store_cache = None
_vector_store_lock = threading.Lock()
_background_sync_state = {"inflight": False}
_background_sync_lock = threading.Lock()

_cloud_circuit_breaker = {
    "consecutive_failures": 0,
    "bypass_until": 0.0,
}
CLOUD_FAILURE_THRESHOLD = 1
CLOUD_COOLDOWN_SECONDS = 60.0


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _connect_milvus_client(cfg: dict) -> MilvusClient:
    return MilvusClient(uri=cfg["uri"], token=cfg["token"], timeout=MILVUS_TIMEOUT_SECONDS)


def _connect_milvus_client_with_timeout(cfg: dict, timeout_seconds: float) -> MilvusClient:
    return MilvusClient(uri=cfg["uri"], token=cfg["token"], timeout=timeout_seconds)


def _ensure_langchain_milvus_connection(cfg: dict) -> None:
    try:
        connections.disconnect(alias="default")
    except Exception:
        pass
    connections.connect(
        alias="default",
        uri=cfg["uri"],
        token=cfg["token"],
        timeout=MILVUS_INIT_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

def _mark_milvus_unhealthy(error: str) -> None:
    _milvus_health["last_error"] = error
    _milvus_health["unhealthy_until"] = time.monotonic() + MILVUS_CIRCUIT_BREAKER_SECONDS


def _milvus_circuit_open() -> bool:
    return time.monotonic() < _milvus_health["unhealthy_until"]


def _milvus_endpoint_reachable(cfg: dict) -> bool:
    return True


def _milvus_cloud_ready() -> bool:
    return _get_cloud_config() is not None


# ---------------------------------------------------------------------------
# Schema management
# ---------------------------------------------------------------------------

def collection_exists(cfg: dict) -> bool:
    return _connect_milvus_client(cfg).has_collection(cfg["collection"])


def _get_embedding_dimension(embeddings: OllamaEmbeddings) -> int:
    return len(embeddings.embed_query("dimension probe"))


def _wait_for_collection_presence(
    client: MilvusClient, collection_name: str, timeout_seconds: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if client.has_collection(collection_name):
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for collection '{collection_name}' to become available")


def _wait_for_collection_absence(
    client: MilvusClient, collection_name: str, timeout_seconds: float = 10.0
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if not client.has_collection(collection_name):
                return
        except Exception:
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for collection '{collection_name}' to be dropped")


def ensure_collection_schema(cfg: dict, embeddings, recreate: bool = False) -> bool:
    """Create or verify the Milvus collection schema before ingestion."""
    client = _connect_milvus_client(cfg)
    exists = client.has_collection(cfg["collection"])

    if exists and recreate:
        logger.info("Dropping existing Milvus collection: %s", cfg["collection"])
        client.drop_collection(cfg["collection"])
        _wait_for_collection_absence(client, cfg["collection"])
        exists = False

    if exists:
        return True

    dim = _get_embedding_dimension(embeddings)
    logger.info("Creating Milvus collection '%s' with vector dim=%s", cfg["collection"], dim)

    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="page_number", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(
        fields=fields,
        description="AcademeRAG document chunks",
        enable_dynamic_field=True,
    )
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(
        collection_name=cfg["collection"],
        schema=schema,
        index_params=index_params,
        auto_id=True,
    )
    _wait_for_collection_presence(client, cfg["collection"])

    try:
        idx_params = client.prepare_index_params()
        idx_params.add_index(field_name="source", index_name="source_idx", index_type="INVERTED")
        idx_params.add_index(field_name="page_number", index_name="page_number_idx", index_type="INVERTED")
        idx_params.add_index(field_name="chunk_index", index_name="chunk_index_idx", index_type="INVERTED")
        client.create_index(collection_name=cfg["collection"], index_params=idx_params)
    except Exception as e:
        logger.warning("Failed to create scalar indexes: %s", e)

    return True


def _build_langchain_vector_store(cfg: dict, embeddings: OllamaEmbeddings) -> Milvus:
    conn_args = {"uri": cfg["uri"], "token": cfg["token"]}
    _ensure_langchain_milvus_connection(cfg)
    return Milvus(
        collection_name=cfg["collection"],
        embedding_function=embeddings,
        connection_args={**conn_args, "alias": "default", "timeout": MILVUS_INIT_TIMEOUT_SECONDS},
        primary_field="pk",
        text_field="text",
        vector_field="vector",
        enable_dynamic_field=True,
        timeout=MILVUS_INIT_TIMEOUT_SECONDS,
    )


# ---------------------------------------------------------------------------
# Search executors
# ---------------------------------------------------------------------------

def _search_milvus_with_config(
    cfg: dict, query_vector: list[float], k: int,
    target_sources: Optional[set[str]], timeout_sec: float
) -> list[Document]:
    if not cfg:
        return []
    source_expr = _milvus_source_filter_expr(target_sources or set())
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=timeout_sec)
    try:
        if client.has_collection(cfg["collection"]):
            client.load_collection(cfg["collection"])
    except Exception as load_exc:
        logger.warning("Failed to load Milvus collection '%s': %s", cfg["collection"], load_exc)

    search_kwargs = {
        "collection_name": cfg["collection"],
        "data": [query_vector],
        "anns_field": "vector",
        "search_params": {"metric_type": "COSINE", "params": {"ef": 64}},
        "limit": k,
        "output_fields": ["text", "source", "document_path", "document_hash", "page_number", "chunk_index"],
        "timeout": timeout_sec,
    }
    if source_expr:
        search_kwargs["filter"] = source_expr

    try:
        rows = client.search(**search_kwargs)
    except Exception as e:
        if "does not exist" in str(e) or "collection" in str(e).lower():
            logger.warning(
                "Milvus collection '%s' does not exist; returning empty list. Error: %s",
                cfg["collection"], e
            )
            return []
        raise e

    hits = rows[0] if rows else []
    docs = []
    for hit in hits:
        if isinstance(hit, dict):
            entity = hit.get("entity") or {}
        else:
            entity = getattr(hit, "entity", {}) or {}
        text = str(entity.get("text") or "")
        if not text:
            continue
        metadata = {key: value for key, value in entity.items() if key != "text"}
        docs.append(Document(page_content=text, metadata=metadata))
    return _filter_docs_by_sources(docs, target_sources or set())


def _search_cloud_milvus(
    query_vector: list[float], question: str, k: int,
    target_sources: Optional[set[str]]
) -> list[Document]:
    logger.info("CLOUD_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()

    cfg = _get_cloud_config()
    if not cfg:
        logger.info(
            "CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Cloud not configured'",
            question
        )
        return []

    if time.monotonic() < _cloud_circuit_breaker["bypass_until"]:
        logger.info(
            "CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Circuit breaker open'",
            question
        )
        return []

    timeout_sec = 5.0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _search_milvus_with_config, cfg, query_vector, k, target_sources, timeout_sec
        )
        docs = future.result(timeout=timeout_sec + 1.0)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "CLOUD_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d",
            question, latency_ms, len(docs)
        )
        _cloud_circuit_breaker["consecutive_failures"] = 0
        return docs
    except concurrent.futures.TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("CLOUD_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f", question, latency_ms)
        _cloud_circuit_breaker["consecutive_failures"] += 1
        if _cloud_circuit_breaker["consecutive_failures"] >= CLOUD_FAILURE_THRESHOLD:
            _cloud_circuit_breaker["bypass_until"] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
            logger.warning("Cloud Milvus circuit breaker OPENED for %.1fs | reason='timeout'", CLOUD_COOLDOWN_SECONDS)
        return []
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'",
            question, latency_ms, exc
        )
        _cloud_circuit_breaker["consecutive_failures"] += 1
        if _cloud_circuit_breaker["consecutive_failures"] >= CLOUD_FAILURE_THRESHOLD:
            _cloud_circuit_breaker["bypass_until"] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
            logger.warning("Cloud Milvus circuit breaker OPENED for %.1fs | reason='failure'", CLOUD_COOLDOWN_SECONDS)
        return []
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)


def _search_local_milvus(
    query_vector: list[float], question: str, k: int,
    target_sources: Optional[set[str]]
) -> list[Document]:
    logger.info("LOCAL_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    cfg = _get_local_config()
    timeout_sec = 3.0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _search_milvus_with_config, cfg, query_vector, k, target_sources, timeout_sec
        )
        docs = future.result(timeout=timeout_sec + 1.0)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "LOCAL_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d",
            question, latency_ms, len(docs)
        )
        return docs
    except concurrent.futures.TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "LOCAL_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f", question, latency_ms
        )
        return []
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "LOCAL_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'",
            question, latency_ms, exc
        )
        return []
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
