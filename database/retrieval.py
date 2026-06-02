"""
database/retrieval.py
---------------------
Hybrid retrieval orchestration: concurrent dense + BM25 search,
Reciprocal Rank Fusion, query preprocessing, context assembly,
and the public _retrieve_docs entry point.
"""

import concurrent.futures
import logging
import re
import time
from typing import List, Optional, Set, Tuple, Union

from langchain_core.documents import Document

from database.config import (
    DYNAMIC_TOP_K_MAX, DYNAMIC_TOP_K_MIN, OLLAMA_BASE_URL,
    TOP_K, _get_milvus_config,
)
from database.bm25 import _expand_neighbors_from_corpus, _search_bm25_fallback
from database.embedding import get_embeddings
from database.metadata import _extract_target_sources, _is_syllabus_query
from database.milvus_client import _search_cloud_milvus, _search_local_milvus
from database.reranker import _cross_encoder_rerank

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dynamic top-k
# ---------------------------------------------------------------------------

def _compute_dynamic_top_k(question: str) -> int:
    qlen = len((question or "").strip())
    if qlen <= 80:
        k = TOP_K
    elif qlen <= 220:
        k = TOP_K + 1
    else:
        k = TOP_K + 2
    return max(DYNAMIC_TOP_K_MIN, min(DYNAMIC_TOP_K_MAX, k))


# ---------------------------------------------------------------------------
# Query preprocessing
# ---------------------------------------------------------------------------

def _preprocess_query(question: str) -> str:
    q = question
    replacements = {
        r'\bcs\b': 'Computer Science',
        r'\bcse\b': 'Computer Science and Engineering',
        r'\bdbms\b': 'Database Management System',
        r'\bml\b': 'Machine Learning',
        r'\bai\b': 'Artificial Intelligence',
        r'\bos\b': 'Operating System',
    }
    for pat, rep in replacements.items():
        q = re.sub(pat, rep, q, flags=re.IGNORECASE)
    return q


# ---------------------------------------------------------------------------
# RRF fusion
# ---------------------------------------------------------------------------

def _rrf_fuse(
    dense_docs: List[Union[Document, Tuple[Document, float]]],
    sparse_docs: List[Union[Document, Tuple[Document, float]]],
    k: int,
) -> List[Document]:
    """Combine dense and sparse results via Reciprocal Rank Fusion (rank constant = 60)."""

    def extract_doc(item):
        return item[0] if isinstance(item, tuple) else item

    def doc_key(doc: Document) -> tuple:
        metadata = doc.metadata or {}
        return (
            metadata.get("source"),
            metadata.get("page_number"),
            metadata.get("chunk_index"),
            doc.page_content if metadata.get("chunk_index") is None else None,
        )

    rrf_scores: dict = {}
    doc_map: dict = {}

    for rank, item in enumerate(dense_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    for rank, item in enumerate(sparse_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    fused_docs = []
    for key in sorted_keys[:k]:
        doc = doc_map[key]
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rrf_score"] = rrf_scores[key]
        fused_docs.append(doc)
    return fused_docs


# ---------------------------------------------------------------------------
# Dense pipeline
# ---------------------------------------------------------------------------

def _dense_search_pipeline(
    question: str, k: int, target_sources: Optional[Set[str]]
) -> list:
    """
    Embed query with bge-m3:latest, then try Milvus Cloud;
    fall back to local Milvus if cloud returns nothing.
    """
    start_time = time.perf_counter()
    cfg = _get_milvus_config()
    query_vector = []
    if cfg:
        try:
            embeddings = get_embeddings()
            query_vector = embeddings.embed_query(question)
        except Exception as exc:
            logger.error("Failed to generate query embeddings: %s", exc)

    docs = []
    fallback_used = False
    if query_vector:
        docs = _search_cloud_milvus(query_vector, question, k, target_sources)
        if not docs:
            docs = _search_local_milvus(query_vector, question, k, target_sources)
            fallback_used = True

    latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "DENSE_PIPELINE_COMPLETED | query='%s' | latency_ms=%.1f | chunk_count=%d | fallback_used=%s",
        question, latency_ms, len(docs), fallback_used,
    )
    return docs


# ---------------------------------------------------------------------------
# Main retrieval orchestrator
# ---------------------------------------------------------------------------

def _retrieve_docs(question: str) -> list:
    """
    Orchestrate concurrent dense + BM25 search, RRF fusion,
    CrossEncoder reranking, and neighbor expansion.
    """
    logger.info("REQUEST_RECEIVED | request_id=- | query='%s'", question)
    question_processed = _preprocess_query(question)
    k = _compute_dynamic_top_k(question_processed)
    target_sources = _extract_target_sources(question_processed)

    if target_sources:
        k = max(k, 6)

    search_k = max(40, k * 4)
    start_time = time.perf_counter()

    dense_docs: list = []
    bm25_docs: list = []
    dense_failed = False
    dense_timeout = False

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        dense_future = executor.submit(_dense_search_pipeline, question_processed, search_k, target_sources)
        bm25_future = executor.submit(_search_bm25_fallback, question_processed, search_k, target_sources)

        try:
            dense_docs = dense_future.result(timeout=15.0)
        except concurrent.futures.TimeoutError:
            dense_failed = True
            dense_timeout = True
            logger.error("Dense search pipeline timed out (15s)")
        except Exception as e:
            dense_failed = True
            logger.error("Dense search pipeline failed: %s", e)

        try:
            bm25_docs = bm25_future.result(timeout=15.0)
        except Exception as e:
            logger.error("BM25 search pipeline failed: %s", e)
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    concurrent_latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "CONCURRENT_SEARCH_COMPLETED | latency_ms=%.1f | dense_count=%d | bm25_count=%d",
        concurrent_latency_ms, len(dense_docs), len(bm25_docs),
    )

    fallback_triggered = len(dense_docs) == 0 or dense_failed
    logger.info(
        "RETRIEVAL_STATS | total_retrieval_latency_ms=%.1f | timeout_triggered=%s | fallback_triggered=%s",
        concurrent_latency_ms, dense_timeout, fallback_triggered,
    )

    fused_docs = _rrf_fuse(dense_docs, bm25_docs, search_k)
    if not fused_docs:
        logger.warning("FUSION_EMPTY | No documents returned from dense or bm25.")
        return []

    logger.info("RERANK_STARTED | request_id=- | chunk_count=%d", len(fused_docs))
    rerank_start_time = time.perf_counter()
    try:
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info(
            "RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d",
            rerank_latency_ms, len(reranked_docs),
        )
        if reranked_docs:
            top_docs = reranked_docs[:max(k, 4)]
            expanded = _expand_neighbors_from_corpus(top_docs)
            logger.info(
                "NEIGHBOR_EXPANSION | input_chunks=%d | expanded_chunks=%d",
                len(top_docs), len(expanded),
            )
            return expanded
        return []
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        expanded = _expand_neighbors_from_corpus(fused_docs[:k])
        return expanded


# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

def _sanitize_context_text(text: str) -> str:
    """Strip or redact prompt injection keywords from retrieved context."""
    if not text:
        return ""
    injection_patterns = [
        r"(?i)ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
        r"(?i)forget\s+(?:all\s+)?(?:previous\s+)?instructions",
        r"(?i)bypass\s+(?:all\s+)?(?:previous\s+)?instructions",
        r"(?i)system\s+prompt",
        r"(?i)jailbreak",
        r"(?i)developer\s+mode",
        r"(?i)do\s+anything\s+now",
        r"(?i)dan\s+mode",
        r"(?i)you\s+are\s+now",
        r"(?i)act\s+as",
        r"(?i)pretend\s+to\s+be",
        r"(?i)forget\s+everything",
        r"(?i)override\s+(?:all\s+)?(?:previous\s+)?instructions",
    ]
    sanitized = text
    for pattern in injection_patterns:
        sanitized = re.sub(pattern, "[redacted command]", sanitized)
    return sanitized


def _format_context(docs, max_chars: int = 32000) -> str:
    docs = sorted(docs, key=lambda d: (
        str((d.metadata or {}).get("source", "")),
        int((d.metadata or {}).get("page_number", 0) or 0),
        int((d.metadata or {}).get("chunk_index", 0) or 0),
    ))
    max_tokens = max_chars // 4
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoder = None

    formatted = []
    if encoder:
        current_tokens = 0
        for doc in docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = _sanitize_context_text(doc.page_content)
            header_tokens = len(encoder.encode(chunk_header))
            content_tokens = len(encoder.encode(content))
            total_chunk_tokens = header_tokens + content_tokens
            if current_tokens + total_chunk_tokens > max_tokens:
                remaining_tokens = max_tokens - current_tokens - header_tokens
                if remaining_tokens > 20:
                    encoded = encoder.encode(content)
                    truncated_content = encoder.decode(encoded[:remaining_tokens])
                    match = list(re.finditer(r'[.!?]\s+', truncated_content))
                    if match:
                        truncated_content = truncated_content[:match[-1].end()].strip()
                    formatted.append(chunk_header + truncated_content + " ... [TRUNCATED]")
                break
            formatted.append(chunk_header + content)
            current_tokens += total_chunk_tokens
    else:
        current_chars = 0
        for doc in docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = _sanitize_context_text(doc.page_content)
            chunk_text = chunk_header + content
            if current_chars + len(chunk_text) > max_chars:
                remaining_chars = max_chars - current_chars
                if remaining_chars > len(chunk_header) + 20:
                    allowed_len = remaining_chars - len(chunk_header)
                    truncated_content = content[:allowed_len]
                    match = list(re.finditer(r'[.!?]\s+', truncated_content))
                    if match:
                        truncated_content = truncated_content[:match[-1].end()].strip()
                    formatted.append(chunk_header + truncated_content + " ... [TRUNCATED]")
                break
            formatted.append(chunk_text)
            current_chars += len(chunk_text) + 2

    return "\n\n".join(formatted)


# ---------------------------------------------------------------------------
# LangChain retriever adapter
# ---------------------------------------------------------------------------

def get_retriever():
    from database.ingestion import get_vector_store
    store = get_vector_store()
    if not store:
        return None
    return store.as_retriever(search_kwargs={"k": TOP_K})
