"""
database/ingestion.py
---------------------
PDF discovery, SHA-256 tracking, batch ingestion orchestration,
background sync, diagnostics, and the get_vector_store / initialize_vector_store
public API consumed by api/views.py and create_milvus_collection.py.
"""

import hashlib
import logging
import os
import threading
from typing import Optional

from langchain_core.documents import Document
from langchain_milvus import Milvus

from database.config import (
    CHUNK_OVERLAP, CHUNK_SIZE, COLLECTION_NAME, DOCUMENTS_DIR,
    EMBEDDING_MODEL, INGEST_BATCH_SIZE, INGEST_MAX_SECONDS,
    MILVUS_HEALTHCHECK_TIMEOUT_SECONDS, MILVUS_INIT_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL, PROJECT_ROOT,
    _env_bool, _get_milvus_config, _chunk_profile,
)
from database.embedding import get_embeddings
from database.milvus_client import (
    _background_sync_lock, _background_sync_state,
    _build_langchain_vector_store, _connect_milvus_client_with_timeout,
    _mark_milvus_unhealthy, _milvus_circuit_open, _milvus_cloud_ready,
    _milvus_endpoint_reachable, _milvus_health,
    _vector_store_cache, _vector_store_lock,
    collection_exists, ensure_collection_schema,
)
from database.metadata import _milvus_source_filter_expr

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PDF discovery
# ---------------------------------------------------------------------------

def get_pdf_files() -> list[str]:
    """Return absolute paths of all PDFs: documents/ folder only (canonical source)."""
    pdf_files: list[str] = []
    if os.path.exists(DOCUMENTS_DIR):
        for filename in sorted(os.listdir(DOCUMENTS_DIR)):
            if filename.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(DOCUMENTS_DIR, filename))
    # Also scan project root for legacy copies; prefer documents/ version on name collision.
    for filename in ["RAG sample 1.pdf", "RAG sample 2.pdf", "RAG sample 3.pdf"]:
        root_path = os.path.join(PROJECT_ROOT, filename)
        if os.path.exists(root_path):
            pdf_files.append(root_path)
    by_name: dict[str, str] = {}
    docs_dir_prefix = os.path.normcase(os.path.abspath(DOCUMENTS_DIR) + os.sep)
    for path in pdf_files:
        name = os.path.basename(path).lower()
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = path
            continue
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized.startswith(docs_dir_prefix):
            by_name[name] = path
    return sorted(by_name.values())


# ---------------------------------------------------------------------------
# File metadata & hashing
# ---------------------------------------------------------------------------

def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _collect_pdf_metadata() -> list[dict]:
    items = []
    for pdf_path in get_pdf_files():
        rel_path = os.path.relpath(pdf_path, PROJECT_ROOT)
        items.append({
            "path": pdf_path,
            "relative_path": rel_path,
            "source": os.path.basename(pdf_path),
            "content_hash": _file_sha256(pdf_path),
        })
    return items


# ---------------------------------------------------------------------------
# Django-model tracking
# ---------------------------------------------------------------------------

def _get_tracking_model():
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
        import django
        from django.apps import apps
        if not apps.ready:
            django.setup()
        from api.models import IndexedDocument
        return IndexedDocument
    except Exception as exc:
        logger.debug("Index tracking model unavailable: %s", exc)
        return None


def _load_tracking_map() -> dict[str, str]:
    model = _get_tracking_model()
    if model is None:
        return {}
    rows = model.objects.filter(
        embedding_model=EMBEDDING_MODEL,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    ).only("document_path", "content_hash")
    return {row.document_path: row.content_hash for row in rows}


def _save_tracking_rows(file_metadata: list[dict]) -> None:
    model = _get_tracking_model()
    if model is None:
        return
    for item in file_metadata:
        model.objects.update_or_create(
            document_path=item["relative_path"],
            defaults={
                "source_name": item["source"],
                "content_hash": item["content_hash"],
                "embedding_model": EMBEDDING_MODEL,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "chunk_profile": _chunk_profile(),
            },
        )
    valid_paths = [item["relative_path"] for item in file_metadata]
    model.objects.exclude(document_path__in=valid_paths).delete()


# ---------------------------------------------------------------------------
# Sync decision logic
# ---------------------------------------------------------------------------

def compute_sync_decision(
    file_metadata: list[dict], tracked_hashes: dict[str, str], force_reindex: bool
) -> tuple[bool, str]:
    if force_reindex:
        return True, "forced"
    if not file_metadata:
        return False, "no-documents"
    if not tracked_hashes:
        return True, "no-tracking-state"
    current_paths = {item["relative_path"] for item in file_metadata}
    tracked_paths = set(tracked_hashes.keys())
    if current_paths != tracked_paths:
        return True, "document-set-changed"
    for item in file_metadata:
        if tracked_hashes.get(item["relative_path"]) != item["content_hash"]:
            return True, f"content-changed:{item['relative_path']}"
    return False, "unchanged"


def compute_rebuild_state(force_reindex: bool = False) -> tuple[bool, str]:
    file_metadata = _collect_pdf_metadata()
    tracked_hashes = _load_tracking_map()
    return compute_sync_decision(file_metadata, tracked_hashes, force_reindex)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _ingest_documents_in_batches(vector_store: Milvus, docs: list[Document]) -> None:
    import time
    total = len(docs)
    start = time.monotonic()
    logger.info(
        "Starting Milvus ingestion for %s chunk(s) with batch size %s (timeout %.0fs).",
        total, INGEST_BATCH_SIZE, INGEST_MAX_SECONDS,
    )
    for offset in range(0, total, INGEST_BATCH_SIZE):
        elapsed = time.monotonic() - start
        if elapsed > INGEST_MAX_SECONDS:
            raise TimeoutError(
                f"Ingestion timed out after {elapsed:.1f}s (limit {INGEST_MAX_SECONDS:.1f}s)"
            )
        batch = docs[offset: offset + INGEST_BATCH_SIZE]
        batch_start = time.monotonic()
        vector_store.add_documents(batch)
        completed = min(offset + len(batch), total)
        percent = (completed / total) * 100.0
        batch_elapsed = time.monotonic() - batch_start
        avg_per_chunk = (time.monotonic() - start) / completed
        remaining_chunks = total - completed
        eta = remaining_chunks * avg_per_chunk
        logger.info(
            "Ingestion progress: %s/%s chunks (%.1f%%) | batch %.2fs | elapsed %.1fs | eta %.1fs",
            completed, total, percent, batch_elapsed, time.monotonic() - start, eta,
        )
    logger.info("Milvus ingestion completed in %.1fs.", time.monotonic() - start)


def _ingest_documents_with_client(cfg: dict, embeddings, docs: list[Document]) -> None:
    import time
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=MILVUS_INIT_TIMEOUT_SECONDS)
    total = len(docs)
    start = time.monotonic()
    logger.info(
        "Starting Milvus client ingestion for %s chunk(s) with batch size %s (timeout %.0fs).",
        total, INGEST_BATCH_SIZE, INGEST_MAX_SECONDS,
    )
    for offset in range(0, total, INGEST_BATCH_SIZE):
        elapsed = time.monotonic() - start
        if elapsed > INGEST_MAX_SECONDS:
            raise TimeoutError(
                f"Ingestion timed out after {elapsed:.1f}s (limit {INGEST_MAX_SECONDS:.1f}s)"
            )
        batch = docs[offset: offset + INGEST_BATCH_SIZE]
        batch_texts = [doc.page_content for doc in batch]
        batch_vectors = embeddings.embed_documents(batch_texts)
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"Embedding size mismatch: got {len(batch_vectors)} vectors for {len(batch)} chunks"
            )
        payload = []
        for doc, vector in zip(batch, batch_vectors):
            meta = doc.metadata or {}
            row = {
                "text": doc.page_content,
                "vector": vector,
                "source": str(meta.get("source", ""))[:1024],
                "page_number": int(meta.get("page_number", 0)),
                "chunk_index": int(meta.get("chunk_index", 0)),
            }
            for k, v in meta.items():
                if k not in ["source", "page_number", "chunk_index"]:
                    row[k] = v
            payload.append(row)

        batch_start = time.monotonic()
        client.insert(collection_name=cfg["collection"], data=payload)
        completed = min(offset + len(batch), total)
        percent = (completed / total) * 100.0
        batch_elapsed = time.monotonic() - batch_start
        avg_per_chunk = (time.monotonic() - start) / completed
        remaining_chunks = total - completed
        eta = remaining_chunks * avg_per_chunk
        logger.info(
            "Client ingestion progress: %s/%s chunks (%.1f%%) | batch %.2fs | elapsed %.1fs | eta %.1fs",
            completed, total, percent, batch_elapsed, time.monotonic() - start, eta,
        )
    logger.info("Milvus client ingestion completed in %.1fs.", time.monotonic() - start)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def _source_index_status() -> list[dict]:
    file_metadata = _collect_pdf_metadata()
    tracked_hashes = _load_tracking_map()
    by_source = {
        item["source"]: {
            "source": item["source"],
            "document_path": item["relative_path"],
            "tracked": tracked_hashes.get(item["relative_path"]) is not None,
            "hash_match": tracked_hashes.get(item["relative_path"]) == item["content_hash"],
            "milvus_chunks": None,
            "milvus_count_error": None,
        }
        for item in file_metadata
    }
    cfg = _get_milvus_config()
    if cfg is None:
        return list(by_source.values())
    try:
        client = _connect_milvus_client_with_timeout(
            cfg, timeout_seconds=max(3.0, MILVUS_HEALTHCHECK_TIMEOUT_SECONDS)
        )
        for source, status in by_source.items():
            expr = _milvus_source_filter_expr({source})
            if not expr:
                continue
            try:
                rows = client.query(
                    collection_name=cfg["collection"],
                    filter=expr,
                    output_fields=["source"],
                    limit=16384,
                )
                status["milvus_chunks"] = len(rows)
            except Exception as source_exc:
                status["milvus_count_error"] = str(source_exc)
    except Exception as exc:
        error = str(exc)
        for status in by_source.values():
            status["milvus_count_error"] = error
    return list(by_source.values())


def get_retrieval_diagnostics() -> dict:
    from database.config import (
        COLLECTION_NAME, DYNAMIC_TOP_K_MAX, DYNAMIC_TOP_K_MIN,
        EMBEDDING_MODEL, RELEVANCE_SCORE_THRESHOLD, TOP_K, _chunk_profile,
    )
    should_rebuild, reason = compute_rebuild_state(force_reindex=False)
    return {
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_profile": _chunk_profile(),
        "base_top_k": TOP_K,
        "dynamic_top_k_min": DYNAMIC_TOP_K_MIN,
        "dynamic_top_k_max": DYNAMIC_TOP_K_MAX,
        "score_threshold": RELEVANCE_SCORE_THRESHOLD,
        "should_rebuild": should_rebuild,
        "rebuild_reason": reason,
        "milvus_cloud_ready": _milvus_cloud_ready(),
        "sources": _source_index_status(),
    }


# ---------------------------------------------------------------------------
# Vector store lifecycle
# ---------------------------------------------------------------------------

def _schedule_vector_store_refresh(
    force_reindex: bool = False, recreate_collection_on_sync: bool = True
) -> None:
    cfg = _get_milvus_config()
    if cfg is None or _milvus_circuit_open():
        return
    with _background_sync_lock:
        if _background_sync_state["inflight"]:
            return
        _background_sync_state["inflight"] = True

    def _runner():
        global _vector_store_cache
        try:
            from database import milvus_client as _mc
            store = initialize_vector_store(
                force_reindex=force_reindex,
                recreate_collection_on_sync=recreate_collection_on_sync,
                allow_background_sync=False,
            )
            if store is not None:
                with _mc._vector_store_lock:
                    _mc._vector_store_cache = store
        finally:
            with _background_sync_lock:
                _background_sync_state["inflight"] = False

    threading.Thread(target=_runner, daemon=True).start()


def initialize_vector_store(
    force_reindex: bool = False,
    recreate_collection_on_sync: bool = True,
    allow_background_sync: bool = True,
):
    from database.chunking import _load_and_chunk_files

    cfg = _get_milvus_config()
    if cfg is None:
        return None
    if not _milvus_endpoint_reachable(cfg):
        return None

    embeddings = get_embeddings()
    file_metadata = _collect_pdf_metadata()
    tracked_hashes = _load_tracking_map()
    auto_sync = _env_bool("ACADEMERAG_AUTO_SYNC_INDEX", default=True)
    should_sync, reason = compute_sync_decision(file_metadata, tracked_hashes, force_reindex)
    should_sync = should_sync and auto_sync

    try:
        if should_sync:
            if allow_background_sync and not force_reindex:
                logger.info("Scheduling background Milvus sync due to reason: %s", reason)
                _schedule_vector_store_refresh(
                    force_reindex=True,
                    recreate_collection_on_sync=recreate_collection_on_sync,
                )
                should_sync = False
            else:
                docs = _load_and_chunk_files(file_metadata)
                if not docs:
                    logger.error("No chunkable PDF content found; cannot build vector index.")
                    return None
                logger.info("Rebuilding Milvus collection due to sync reason: %s", reason)
                ensure_collection_schema(cfg, embeddings, recreate=recreate_collection_on_sync)
                _ingest_documents_with_client(cfg, embeddings, docs)
                _save_tracking_rows(file_metadata)
                try:
                    vector_store = _build_langchain_vector_store(cfg, embeddings)
                    vector_store.similarity_search("index readiness probe", k=1)
                except Exception as wrapper_exc:
                    logger.warning(
                        "Milvus ingestion succeeded but LangChain wrapper init failed; "
                        "using direct Milvus client retrieval path. Error: %s",
                        wrapper_exc,
                    )
                    _milvus_health["last_error"] = None
                    _milvus_health["unhealthy_until"] = 0.0
                    return None
                logger.info("Milvus vector store operational.")
                _milvus_health["last_error"] = None
                _milvus_health["unhealthy_until"] = 0.0
                return vector_store

        if not should_sync:
            ensure_collection_schema(cfg, embeddings, recreate=False)
            try:
                vector_store = _build_langchain_vector_store(cfg, embeddings)
            except Exception as wrapper_exc:
                logger.warning(
                    "LangChain Milvus wrapper unavailable; using direct Milvus client retrieval path. "
                    "Error: %s",
                    wrapper_exc,
                )
                _milvus_health["last_error"] = None
                _milvus_health["unhealthy_until"] = 0.0
                return None
            if reason == "unchanged":
                logger.info("Milvus index unchanged; using existing collection.")
            elif not auto_sync:
                logger.info("Milvus index auto-sync disabled; using existing collection.")

        vector_store.similarity_search("index readiness probe", k=1)
        logger.info("Milvus vector store operational.")
        _milvus_health["last_error"] = None
        _milvus_health["unhealthy_until"] = 0.0
        return vector_store
    except Exception as exc:
        _mark_milvus_unhealthy(str(exc))
        logger.error("Error initializing vector store: %s", exc)
        return None


def get_vector_store():
    from database import milvus_client as _mc

    with _mc._vector_store_lock:
        if _mc._vector_store_cache is not None:
            return _mc._vector_store_cache

    store = initialize_vector_store(force_reindex=False, allow_background_sync=True)
    if store:
        with _mc._vector_store_lock:
            _mc._vector_store_cache = store
        return store

    if _milvus_cloud_ready():
        logger.error("Failed to create vector store")
    return None
