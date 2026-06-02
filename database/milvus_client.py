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
    _milvus_endpoint_reachable, _validate_milvus_connection,
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

# ---------------------------------------------------------------------------
# Django-cache-backed circuit breaker state constants
# ---------------------------------------------------------------------------
_CB_STATE_KEY = "milvus_cb_state"
_CB_FAILURES_KEY = "milvus_cb_failures"
_CB_SUCCESSES_KEY = "milvus_cb_successes"
_CB_LOCK_KEY = "milvus_recovery_monitor_lock"

_CB_CLOSED = "CLOSED"
_CB_OPEN = "OPEN"
_CB_HALF_OPEN = "HALF_OPEN"

# Failures before OPEN; OPEN timeout handled by Django cache `timeout` arg.
_CB_FAILURE_THRESHOLD = 2
_CB_REQUIRED_SUCCESSES = 3  # HALF_OPEN -> CLOSED
_CB_OPEN_TIMEOUT_S = 60

# Backward-compat local fallback (used when Django cache is unavailable).
_local_cb = {
    "state": _CB_CLOSED,
    "failures": 0,
    "successes": 0,
    "bypass_until": 0.0,
}


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


# ---------------------------------------------------------------------------
# Django-cache-backed circuit breaker
# ---------------------------------------------------------------------------

def _cache_get(key: str, default=None):
    """Retrieve from Django cache, fall back gracefully on ImportError."""
    try:
        from django.core.cache import cache
        val = cache.get(key)
        return val if val is not None else default
    except Exception:
        return default


def _cache_set(key: str, value, timeout=None):
    """Store in Django cache, fall back gracefully on ImportError."""
    try:
        from django.core.cache import cache
        if timeout is not None:
            cache.set(key, value, timeout=timeout)
        else:
            cache.set(key, value)
    except Exception:
        pass


def _cache_add(key: str, value, timeout=None) -> bool:
    """Atomic cache.add (returns True if the key was newly set)."""
    try:
        from django.core.cache import cache
        return cache.add(key, value, timeout=timeout)
    except Exception:
        return True  # Fail-open: allow monitor to run


def _get_cb_state() -> str:
    """Read circuit breaker state from Django cache (default CLOSED)."""
    return _cache_get(_CB_STATE_KEY, _CB_CLOSED)


def _handle_cloud_success() -> None:
    """Record a successful cloud probe and advance circuit breaker state."""
    state = _get_cb_state()
    if state == _CB_HALF_OPEN:
        successes = _cache_get(_CB_SUCCESSES_KEY, 0) + 1
        _cache_set(_CB_SUCCESSES_KEY, successes)
        if successes >= _CB_REQUIRED_SUCCESSES:
            _cache_set(_CB_STATE_KEY, _CB_CLOSED)
            _cache_set(_CB_FAILURES_KEY, 0)
            _cache_set(_CB_SUCCESSES_KEY, 0)
            logger.info(
                "Cloud Milvus circuit breaker CLOSED after %d consecutive successes.",
                _CB_REQUIRED_SUCCESSES,
            )
        else:
            logger.debug(
                "Cloud Milvus HALF_OPEN: success %d/%d", successes, _CB_REQUIRED_SUCCESSES
            )
    else:
        # CLOSED — just reset failure count
        _cache_set(_CB_FAILURES_KEY, 0)
        _cache_set(_CB_SUCCESSES_KEY, 0)


def _handle_cloud_failure(exc: Exception) -> None:
    """Record a cloud probe failure and open/keep circuit breaker."""
    state = _get_cb_state()
    failures = _cache_get(_CB_FAILURES_KEY, 0) + 1
    _cache_set(_CB_FAILURES_KEY, failures)

    if failures >= _CB_FAILURE_THRESHOLD or state == _CB_HALF_OPEN:
        # Write OPEN with a TTL so it auto-expires to HALF_OPEN
        _cache_set(_CB_STATE_KEY, _CB_OPEN, timeout=_CB_OPEN_TIMEOUT_S)
        _cache_set(_CB_SUCCESSES_KEY, 0)
        logger.warning(
            "Cloud Milvus circuit breaker OPENED (failures=%d, reason=%s).",
            failures, exc,
        )


def _cloud_circuit_open() -> bool:
    """Return True when the circuit breaker is OPEN (cloud should be skipped)."""
    state = _get_cb_state()
    # When the OPEN key has TTL-expired, Django cache returns None -> CLOSED (default).
    # After timeout the state becomes CLOSED again, first probe re-opens to HALF_OPEN.
    return state == _CB_OPEN


def _transition_to_half_open_if_needed() -> bool:
    """If the OPEN timeout expired (state now CLOSED by default), mark HALF_OPEN."""
    state = _get_cb_state()
    if state == _CB_CLOSED:
        # Check if we *were* OPEN and the cache TTL just expired (no prior HALF_OPEN set)
        # We distinguish this by checking failure count > 0
        failures = _cache_get(_CB_FAILURES_KEY, 0)
        if failures >= _CB_FAILURE_THRESHOLD:
            _cache_set(_CB_STATE_KEY, _CB_HALF_OPEN)
            _cache_set(_CB_SUCCESSES_KEY, 0)
            logger.info("Cloud Milvus circuit breaker moved to HALF_OPEN.")
            return True
    return state == _CB_HALF_OPEN


def _milvus_cloud_ready() -> bool:
    return _get_cloud_config() is not None


# ---------------------------------------------------------------------------
# Background cloud recovery monitor (distributed lock via Django cache)
# ---------------------------------------------------------------------------

_recovery_monitor_started = False
_recovery_monitor_lock = threading.Lock()


def _start_cloud_recovery_monitor() -> None:
    """Launch the background recovery monitor thread once per process."""
    global _recovery_monitor_started
    with _recovery_monitor_lock:
        if _recovery_monitor_started:
            return
        _recovery_monitor_started = True

    def _monitor():
        logger.info("Cloud recovery monitor started (interval=300s).")
        while True:
            time.sleep(300)  # 5-minute polling interval
            try:
                # Distributed lock: only one Django worker runs the check
                acquired = _cache_add(_CB_LOCK_KEY, "running", timeout=300)
                if not acquired:
                    logger.debug("Recovery monitor: lock held by another worker; skipping.")
                    continue

                cfg = _get_cloud_config()
                if not cfg:
                    continue

                # Require 3 consecutive successful probes before recovery
                all_good = True
                for attempt in range(1, _CB_REQUIRED_SUCCESSES + 1):
                    if attempt > 1:
                        time.sleep(2)
                    if not _validate_milvus_connection(cfg):
                        all_good = False
                        logger.debug(
                            "Recovery monitor probe %d/%d failed.",
                            attempt, _CB_REQUIRED_SUCCESSES,
                        )
                        break
                    logger.debug(
                        "Recovery monitor probe %d/%d succeeded.",
                        attempt, _CB_REQUIRED_SUCCESSES,
                    )

                if all_good:
                    _cache_set(_CB_STATE_KEY, _CB_CLOSED)
                    _cache_set(_CB_FAILURES_KEY, 0)
                    _cache_set(_CB_SUCCESSES_KEY, 0)
                    logger.info(
                        "Cloud recovery monitor: Zilliz Cloud connection fully restored and verified."
                    )
            except Exception as exc:
                logger.debug("Recovery monitor iteration error: %s", exc)

    t = threading.Thread(target=_monitor, daemon=True, name="milvus-recovery-monitor")
    t.start()


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

    # Check circuit breaker
    _transition_to_half_open_if_needed()
    if _cloud_circuit_open():
        logger.info(
            "CLOUD_SEARCH_SKIPPED | request_id=- | query='%s' | reason='Circuit breaker OPEN'",
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
        _handle_cloud_success()
        return docs
    except concurrent.futures.TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("CLOUD_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f", question, latency_ms)
        _handle_cloud_failure(TimeoutError("Cloud search timed out"))
        return []
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'",
            question, latency_ms, exc
        )
        _handle_cloud_failure(exc)
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


# ---------------------------------------------------------------------------
# Collection compatibility validator
# ---------------------------------------------------------------------------

def validate_collection_compatibility(cfg: dict, expected_dim: int) -> bool:
    """Verify that the named collection exists and has the expected vector dim."""
    try:
        client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=2.0)
        if not client.has_collection(cfg["collection"]):
            return False
        desc = client.describe_collection(cfg["collection"])
        fields = desc.get("fields", []) or []
        vector_field = next(
            (f for f in fields if f.get("name") == "vector"), None
        )
        if not vector_field:
            return False
        dim = int(
            vector_field.get("dim")
            or (vector_field.get("params") or {}).get("dim", 0)
            or 0
        )
        return dim == expected_dim
    except Exception as exc:
        logger.debug("validate_collection_compatibility failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Metadata discrepancy logger (no vector scans)
# ---------------------------------------------------------------------------

def check_and_log_metadata_discrepancies() -> None:
    """Compare local SQLite IndexedDocument count against Milvus collection stats.

    Uses get_collection_stats() (row_count property) instead of scanning
    vector data — no expensive queries are issued.
    """
    local_cfg = _get_local_config()
    cloud_cfg = _get_cloud_config()

    try:
        local_client = _connect_milvus_client_with_timeout(local_cfg, timeout_seconds=2.0)
        local_stats = local_client.get_collection_stats(local_cfg["collection"])
        local_chunks = int(local_stats.get("row_count", 0))
    except Exception as exc:
        logger.debug("Local collection stats unavailable: %s", exc)
        local_chunks = None

    cloud_chunks = None
    if cloud_cfg and _milvus_endpoint_reachable(cloud_cfg, ttl_seconds=10.0):
        try:
            cloud_client = _connect_milvus_client_with_timeout(cloud_cfg, timeout_seconds=3.0)
            cloud_stats = cloud_client.get_collection_stats(cloud_cfg["collection"])
            cloud_chunks = int(cloud_stats.get("row_count", 0))
        except Exception as exc:
            logger.debug("Cloud collection stats unavailable: %s", exc)

    if local_chunks is not None and cloud_chunks is not None:
        if local_chunks != cloud_chunks:
            logger.warning(
                "METADATA_DISCREPANCY_DETECTED | local_chunks=%d | cloud_chunks=%d",
                local_chunks, cloud_chunks,
            )
        else:
            logger.info(
                "METADATA_SYNC_OK | chunks=%d (local=cloud)", local_chunks
            )

    try:
        from api.models import IndexedDocument  # deferred to avoid app-not-ready errors
        doc_count = IndexedDocument.objects.count()
        logger.info("INDEXED_DOCUMENT_COUNT | documents=%d", doc_count)
    except Exception as exc:
        logger.debug("IndexedDocument count unavailable: %s", exc)
