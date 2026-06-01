"""
database/bm25.py
----------------
BM25 index: build, persist, load, tokenize, and retrieval.
Maintains the in-process corpus cache and adjacency map used by
the sparse leg of the hybrid retrieval pipeline.
"""

import logging
import math
import os
import pickle
import threading
from collections import Counter, defaultdict
from typing import Any, Optional

from langchain_core.documents import Document

from database.config import (
    BM25_B, BM25_K1, PROJECT_ROOT, STOPWORDS
)
from database.metadata import (
    _doc_source, _document_score, _is_syllabus_query, _tokenize
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global BM25 state
# ---------------------------------------------------------------------------

BM25_INDEX_FILE = os.path.join(PROJECT_ROOT, "bm25_index.pkl")

_fallback_cache_lock = threading.Lock()
_fallback_cache_state: dict[str, Any] = {
    "corpus": tuple(),
    "stats": None,
    "signature": None,
    "inflight": False,
}

_adjacency_map: dict[tuple, Document] = {}
_adjacency_map_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Corpus stats builder
# ---------------------------------------------------------------------------

def _build_fallback_stats_from_docs(docs: tuple[Document, ...]) -> dict[str, Any]:
    """Build inverted index + BM25 corpus stats from a document corpus."""
    inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_lengths: list[int] = []
    total_length = 0

    for idx, doc in enumerate(docs):
        tokens = _tokenize(doc.page_content)
        length = len(tokens)
        doc_lengths.append(length)
        total_length += length
        tf = Counter(tokens)
        for token, count in tf.items():
            inverted_index[token].append((idx, count))

    avg_doc_length = (total_length / len(docs)) if docs else 0.0
    return {
        "corpus": docs,
        "inverted_index": dict(inverted_index),
        "doc_lengths": doc_lengths,
        "avg_doc_length": avg_doc_length,
        "doc_count": len(docs),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _refresh_fallback_cache() -> None:
    from database.ingestion import _collect_pdf_metadata
    from database.chunking import _load_and_chunk_files, _fallback_signature

    file_metadata = _collect_pdf_metadata()
    docs = tuple(_load_and_chunk_files(file_metadata))
    stats = _build_fallback_stats_from_docs(docs)
    signature = _fallback_signature(file_metadata)

    with _fallback_cache_lock:
        _fallback_cache_state["corpus"] = docs
        _fallback_cache_state["stats"] = stats
        _fallback_cache_state["signature"] = signature
        _fallback_cache_state["inflight"] = False

    _build_adjacency_map(docs)

    try:
        import filelock
        lock = filelock.FileLock(BM25_INDEX_FILE + ".lock")
        with lock.acquire(timeout=30):
            tmp_file = BM25_INDEX_FILE + f".{os.getpid()}.tmp"
            with open(tmp_file, "wb") as f:
                pickle.dump({"signature": signature, "corpus": docs, "stats": stats}, f)
            os.replace(tmp_file, BM25_INDEX_FILE)
    except Exception as e:
        logger.warning("Failed to persist BM25 index: %s", e)


def _load_persisted_bm25() -> bool:
    if not os.path.exists(BM25_INDEX_FILE):
        return False
    try:
        from database.ingestion import _collect_pdf_metadata
        from database.chunking import _fallback_signature

        with open(BM25_INDEX_FILE, "rb") as f:
            data = pickle.load(f)

        current_sig = _fallback_signature(_collect_pdf_metadata())
        if data["signature"] == current_sig:
            with _fallback_cache_lock:
                _fallback_cache_state["corpus"] = data["corpus"]
                _fallback_cache_state["stats"] = data["stats"]
                _fallback_cache_state["signature"] = data["signature"]
                _fallback_cache_state["inflight"] = False
            _build_adjacency_map(data["corpus"])
            return True
    except Exception as e:
        logger.warning("Failed to load persisted BM25 index: %s", e)
    return False


def _init_bm25_index_at_startup() -> None:
    if _load_persisted_bm25():
        logger.info("BM25 index loaded successfully at startup.")
        return

    logger.info("BM25 index missing or stale at startup. Building synchronously under lock.")
    try:
        import filelock
        lock = filelock.FileLock(BM25_INDEX_FILE + ".build.lock")
        with lock.acquire(timeout=300):
            if _load_persisted_bm25():
                logger.info("BM25 index built by another worker. Loaded successfully.")
                return
            logger.info("Building BM25 index...")
            _refresh_fallback_cache()
    except Exception as e:
        logger.error("Failed to initialize BM25 index at startup: %s", e)


# ---------------------------------------------------------------------------
# Corpus accessors
# ---------------------------------------------------------------------------

def _fallback_chunk_corpus() -> tuple[Document, ...]:
    with _fallback_cache_lock:
        cached_corpus = _fallback_cache_state["corpus"]
    if cached_corpus:
        return cached_corpus
    logger.warning("Local BM25 corpus unavailable; failing fast.")
    return tuple()


def _fallback_corpus_stats() -> dict:
    with _fallback_cache_lock:
        stats = _fallback_cache_state["stats"]
    if stats is not None:
        return stats
    logger.warning("Local BM25 index unavailable; failing fast.")
    return {
        "corpus": tuple(),
        "inverted_index": {},
        "doc_lengths": [],
        "avg_doc_length": 1.0,
        "doc_count": 0,
    }


# ---------------------------------------------------------------------------
# BM25 scoring (legacy, kept for compatibility)
# ---------------------------------------------------------------------------

def _bm25_score(query_terms: list[str], doc_index: int, stats: dict) -> float:
    if not query_terms or stats.get("doc_count", 0) == 0:
        return 0.0
    inverted_index = stats.get("inverted_index", {})
    doc_lengths = stats.get("doc_lengths", [])
    avg_doc_length = stats.get("avg_doc_length", 1.0)
    doc_count = stats.get("doc_count", 0)
    score = 0.0
    for term in query_terms:
        if term not in inverted_index:
            continue
        postings = inverted_index[term]
        df = len(postings)
        freq = next((f for d, f in postings if d == doc_index), 0)
        if freq == 0:
            continue
        idf = max(0.0, math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5))))
        doc_length = doc_lengths[doc_index] if doc_index < len(doc_lengths) else 1
        numerator = freq * (BM25_K1 + 1.0)
        denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * (doc_length / avg_doc_length))
        score += idf * (numerator / denominator)
    return score


# ---------------------------------------------------------------------------
# BM25 retrieval
# ---------------------------------------------------------------------------

def _fallback_retrieve_docs(
    question: str, k: int, target_sources: Optional[set[str]] = None
) -> list[Document]:
    """Retrieve documents via inverted-index BM25 scoring (sparse leg)."""
    stats = _fallback_corpus_stats()
    corpus = stats["corpus"]
    if not corpus:
        return []

    allowed_sources = {source.lower() for source in (target_sources or set())}
    query_tokens = _tokenize(question)
    query_terms = [token for token in query_tokens if token not in STOPWORDS]

    if not query_terms:
        filtered = [
            doc for doc in corpus
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    inverted_index = stats["inverted_index"]
    doc_lengths = stats["doc_lengths"]
    avg_doc_length = stats["avg_doc_length"] or 1.0
    doc_count = stats["doc_count"]

    scores: dict[int, float] = defaultdict(float)
    for term in query_terms:
        if term not in inverted_index:
            continue
        postings = inverted_index[term]
        df = len(postings)
        idf = max(0.0, math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5))))
        for doc_index, freq in postings:
            doc_length = doc_lengths[doc_index] or 1
            numerator = freq * (BM25_K1 + 1.0)
            denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * (doc_length / avg_doc_length))
            scores[doc_index] += idf * (numerator / denominator)

    scored: list[tuple[float, float, float, Document]] = []
    for doc_index, lexical_score in scores.items():
        doc = corpus[doc_index]
        if allowed_sources and _doc_source(doc).lower() not in allowed_sources:
            continue
        heuristic_score, heuristic_boost, page_bias = _document_score(question, doc)
        score = lexical_score
        if _is_syllabus_query(question):
            score += heuristic_boost
        else:
            score += heuristic_score * 0.15
        if score > 0:
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "score": score},
            )
            scored.append((score, heuristic_boost, page_bias, doc_with_score))

    if not scored:
        filtered = [
            doc for doc in corpus
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    primary_docs = [doc for _, _, _, doc in scored[:k]]
    return primary_docs[:max(k, 4)]


# ---------------------------------------------------------------------------
# Adjacency map (for neighbor expansion)
# ---------------------------------------------------------------------------

def _build_adjacency_map(corpus) -> None:
    local_map: dict[tuple, Document] = {}
    for doc in corpus:
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        chunk_index = metadata.get("chunk_index")
        if document_path is not None and chunk_index is not None:
            local_map[(document_path, int(chunk_index))] = doc
    with _adjacency_map_lock:
        global _adjacency_map
        _adjacency_map = local_map


def _expand_neighbors_from_corpus(
    docs: list[Document], include_adjacent: bool = True
) -> list[Document]:
    """Expand retrieved docs with their immediately adjacent chunks from the BM25 corpus."""
    with _adjacency_map_lock:
        lookup = _adjacency_map

    if not lookup:
        corpus = _fallback_chunk_corpus()
        if corpus:
            _build_adjacency_map(corpus)
            with _adjacency_map_lock:
                lookup = _adjacency_map
        if not lookup:
            return docs

    seen_keys: set[tuple] = set()
    result: list[Document] = []

    for doc in docs:
        meta = doc.metadata or {}
        dp = meta.get("document_path")
        ci = meta.get("chunk_index")
        key = (dp, ci if ci is None else int(ci))

        if key not in seen_keys:
            seen_keys.add(key)
            result.append(doc)

        if not include_adjacent or dp is None or ci is None:
            continue

        for offset in (-1, 1):
            neighbor_key = (dp, int(ci) + offset)
            if neighbor_key not in seen_keys and neighbor_key in lookup:
                seen_keys.add(neighbor_key)
                neighbor = lookup[neighbor_key]
                neighbor = Document(
                    page_content=neighbor.page_content,
                    metadata={**neighbor.metadata, "_neighbor_expanded": True},
                )
                result.append(neighbor)

    return result


# ---------------------------------------------------------------------------
# BM25 search wrapper (for retrieval.py)
# ---------------------------------------------------------------------------

def _search_bm25_fallback(
    question: str, k: int, target_sources: Optional[set[str]]
) -> list[Document]:
    """BM25 sparse-leg search wrapper used by parallel retrieval orchestrator."""
    import time
    logger.info("BM25_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    try:
        docs = _fallback_retrieve_docs(question, k, target_sources=target_sources)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "BM25_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d",
            question, latency_ms, len(docs)
        )
        return docs
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning(
            "BM25_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'",
            question, latency_ms, exc
        )
        return []
