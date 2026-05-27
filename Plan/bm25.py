import math
import time
import logging
from collections import Counter, defaultdict
from typing import Any
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

BM25_K1 = 1.5
BM25_B = 0.75

def _build_fallback_stats_from_docs(docs: tuple[Document, ...]) -> dict[str, Any]:
    """
    Build optimized inverted index and corpus statistics for fast BM25 retrieval.
    This replaces the previous slow list-of-Counters approach and executes efficiently.
    """
    # inverted_index maps term -> list of (doc_index, term_frequency)
    inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_lengths = []
    total_length = 0

    # We rely on the existing _tokenize from Milvus.py context
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

def _fallback_retrieve_docs(question: str, k: int, target_sources: set[str] | None = None) -> list[Document]:
    """
    Retrieve documents using the inverted index for optimized BM25 scoring.
    Designed to act as the sparse leg of the parallel hybrid search.
    """
    _schedule_fallback_cache_refresh()
    stats = _fallback_corpus_stats()
    corpus = stats["corpus"]
    if not corpus:
        return []
        
    allowed_sources = {source.lower() for source in (target_sources or set())}
    
    query_tokens = _tokenize(question)
    query_terms = [token for token in query_tokens if token not in STOPWORDS]

    if not query_terms:
        # Fallback to returning first k if no usable terms are found
        filtered = [
            doc for doc in corpus 
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    inverted_index = stats["inverted_index"]
    doc_lengths = stats["doc_lengths"]
    avg_doc_length = stats["avg_doc_length"] or 1.0
    doc_count = stats["doc_count"]

    # Calculate BM25 scores efficiently using the inverted index
    scores: dict[int, float] = defaultdict(float)
    
    for term in query_terms:
        if term not in inverted_index:
            continue
            
        postings = inverted_index[term]
        df = len(postings)
        # IDF calculation matching typical BM25 standard formula
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
            
        # Incorporate heuristic scoring
        heuristic_score, heuristic_boost, page_bias = _document_score(question, doc)
        
        score = lexical_score
        if _is_syllabus_query(question):
            score += heuristic_boost
        else:
            score += heuristic_score * 0.15
            
        if score > 0:
            # Propagate the 'score' property in metadata to assist RRF/hybrid combiner
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "score": score}
            )
            scored.append((score, heuristic_boost, page_bias, doc_with_score))

    if not scored:
        filtered = [
            doc for doc in corpus 
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    # Sort primarily by BM25/hybrid score, then heuristic boost, then page bias
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    primary_docs = [doc for _, _, _, doc in scored[:k]]
    
    # Expand neighbor chunks for continuity
    return _expand_neighbor_chunks(primary_docs, max_docs=max(k, 4), allowed_sources=target_sources)

def _search_bm25_fallback(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    """
    Wrapper for BM25 retrieval that acts as the sparse leg of the parallel hybrid search.
    """
    logger.info("BM25_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    try:
        docs = _fallback_retrieve_docs(question, k, target_sources=target_sources)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info("BM25_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d", question, latency_ms, len(docs))
        return docs
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("BM25_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'", question, latency_ms, exc)
        return []

def _bm25_score(query_terms: list[str], doc_index: int, stats: dict) -> float:
    """
    Retained for backwards compatibility if any external caller/test references it,
    but no longer directly used by _fallback_retrieve_docs optimization.
    """
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
