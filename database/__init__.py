"""
database/__init__.py
--------------------
Public API surface for the AcademeRAG database package.

All symbols that external modules (rag/llm_orchestration.py, api/views.py,
create_milvus_collection.py, setup_milvus.py) imported from the old Milvus.py
are re-exported here verbatim so that the calling code only needs to change
its import statement to `from database import ...`.

Import order is deliberate:
  1. milvus_client  — applies MilvusClient monkeypatch FIRST
  2. config         — constants & env helpers
  3. embedding      — embedding wrapper
  4. metadata       — source/syllabus utilities
  5. chunking       — PDF → chunks
  6. bm25           — BM25 index
  7. ingestion      — vector store lifecycle
  8. reranker       — CrossEncoder
  9. retrieval      — orchestrator

Startup side effect: _init_bm25_index_at_startup() is called at the bottom
of this file, exactly mirroring Milvus.py line 2122.
"""

# ---- 1. Apply MilvusClient monkeypatch before any ORM usage ----
import database.milvus_client  # noqa: F401 — side-effect import (monkeypatch)

# ---- 2. Config ----
from database.config import (
    BM25_B,
    BM25_K1,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DOCUMENTS_DIR,
    DYNAMIC_TOP_K_MAX,
    DYNAMIC_TOP_K_MIN,
    EMBEDDING_MODEL,
    INGEST_BATCH_SIZE,
    INGEST_MAX_SECONDS,
    INSUFFICIENT_CONTEXT_MESSAGE,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    MILVUS_CIRCUIT_BREAKER_SECONDS,
    MILVUS_HEALTHCHECK_TIMEOUT_SECONDS,
    MILVUS_INIT_TIMEOUT_SECONDS,
    MILVUS_TIMEOUT_SECONDS,
    OLLAMA_BASE_URL,
    PROJECT_ROOT,
    RELEVANCE_SCORE_THRESHOLD,
    STOPWORDS,
    TOP_K,
    _chunk_profile,
    _env_bool,
    _env_float,
    _env_int,
    _env_str,
    _get_cloud_config,
    _get_deployment_mode,
    _get_local_config,
    _get_milvus_config,
    _looks_like_placeholder,
    _milvus_endpoint_reachable,
    _required_env,
    _validate_milvus_connection,
    _get_active_milvus_mode,
)

# ---- 3. Embedding ----
from database.embedding import (
    get_embedding_dimension as _get_embedding_dimension,
    get_embeddings,
)

# ---- 4. Metadata / query analysis ----
from database.metadata import (
    _augment_docs_for_syllabus,
    _clean_syllabus_text,
    _doc_source,
    _document_score,
    _explicit_unit_title_line_count,
    _extract_target_sources,
    _filter_docs_by_sources,
    _generic_retrieval_boost,
    _has_explicit_support,
    _is_multi_subject_query,
    _is_page_header_line,
    _is_syllabus_noise_heading,
    _is_syllabus_noise_item,
    _is_syllabus_query,
    _is_unit_title_query,
    _milvus_escape_literal,
    _milvus_source_filter_expr,
    _query_keywords,
    _query_subject_phrase,
    _query_subject_phrases,
    _tokenize,
    _unit_heading_count,
)

# ---- 5. Chunking ----
from database.chunking import (
    _fallback_signature,
    _load_and_chunk_files,
    _page_text_map,
    _raw_page_text_map,
)

# ---- 6. BM25 ----
from database.bm25 import (
    BM25_INDEX_FILE,
    _adjacency_map,
    _adjacency_map_lock,
    _bm25_score,
    _build_adjacency_map,
    _build_fallback_stats_from_docs,
    _expand_neighbors_from_corpus,
    _fallback_cache_lock,
    _fallback_cache_state,
    _fallback_chunk_corpus,
    _fallback_corpus_stats,
    _fallback_retrieve_docs,
    _init_bm25_index_at_startup,
    _load_persisted_bm25,
    _refresh_fallback_cache,
    _search_bm25_fallback,
)

# ---- 7. Milvus client ----
from database.milvus_client import (
    _CB_CLOSED,
    _CB_HALF_OPEN,
    _CB_OPEN,
    _background_sync_lock,
    _background_sync_state,
    _build_langchain_vector_store,
    _cache_get,
    _cache_set,
    _cloud_circuit_open,
    _connect_milvus_client,
    _connect_milvus_client_with_timeout,
    _ensure_langchain_milvus_connection,
    _get_cb_state,
    _handle_cloud_failure,
    _handle_cloud_success,
    _mark_milvus_unhealthy,
    _milvus_circuit_open,
    _milvus_cloud_ready,
    _milvus_health,
    _search_cloud_milvus,
    _search_local_milvus,
    _search_milvus_with_config,
    _start_cloud_recovery_monitor,
    _transition_to_half_open_if_needed,
    _vector_store_cache,
    _vector_store_lock,
    check_and_log_metadata_discrepancies,
    collection_exists,
    ensure_collection_schema,
    validate_collection_compatibility,
)

# ---- 8. Ingestion ----
from database.ingestion import (
    _collect_pdf_metadata,
    _file_sha256,
    _get_tracking_model,
    _ingest_documents_in_batches,
    _ingest_documents_with_client,
    _load_tracking_map,
    _save_tracking_rows,
    _schedule_vector_store_refresh,
    _source_index_status,
    compute_rebuild_state,
    compute_sync_decision,
    get_pdf_files,
    get_retrieval_diagnostics,
    get_vector_store,
    initialize_vector_store,
)

# ---- 9. Reranker ----
from database.reranker import (
    _cross_encoder_rerank,
    _get_cross_encoder,
    preload_cross_encoder,
)

# ---- 10. Retrieval ----
from database.retrieval import (
    _compute_dynamic_top_k,
    _dense_search_pipeline,
    _format_context,
    _preprocess_query,
    _retrieve_docs,
    _rrf_fuse,
    get_retriever,
)

# ---------------------------------------------------------------------------
# Startup: launch background Milvus cloud recovery monitor (daemon thread)
# ---------------------------------------------------------------------------
_start_cloud_recovery_monitor()

