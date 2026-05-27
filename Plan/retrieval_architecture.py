import time
import logging
import concurrent.futures
from typing import List, Set, Optional

# Assuming these are available from Milvus.py when merged
# from langchain_core.documents import Document
# from Milvus import (
#     _search_cloud_milvus, 
#     _search_local_milvus, 
#     _search_bm25_fallback, 
#     _preprocess_query, 
#     _compute_dynamic_top_k, 
#     _extract_target_sources, 
#     _cross_encoder_rerank, 
#     _expand_neighbor_chunks
# )

logger = logging.getLogger(__name__)

def _rrf_fuse(dense_docs: list, bm25_docs: list, rrf_k: int = 60) -> list:
    """
    Fuses two lists of documents using Reciprocal Rank Fusion (RRF).
    Also inherently handles deduplication by using document page_content as a unique key.
    """
    scores = {}
    doc_map = {}
    
    def add_docs(docs: list):
        for rank, doc in enumerate(docs):
            key = doc.page_content
            if key not in scores:
                scores[key] = 0.0
                doc_map[key] = doc
            scores[key] += 1.0 / (rank + 1 + rrf_k)
            
    add_docs(dense_docs)
    add_docs(bm25_docs)
    
    # Sort by RRF score descending
    sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)
    return [doc_map[k] for k in sorted_keys]

def _dense_search_pipeline(question: str, k: int, target_sources: Optional[Set[str]]) -> list:
    """
    Tries Milvus Cloud first, falls back to local Milvus if Cloud returns no results or fails.
    """
    start_time = time.perf_counter()
    docs = _search_cloud_milvus(question, k, target_sources)
    fallback_used = False
    
    if not docs:
        docs = _search_local_milvus(question, k, target_sources)
        fallback_used = True
    
    latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info("DENSE_PIPELINE_COMPLETED | query='%s' | latency_ms=%.1f | chunk_count=%d | fallback_used=%s", 
                question, latency_ms, len(docs), fallback_used)
    return docs

def _retrieve_docs(question: str) -> list:
    """
    Main retrieval function orchestrating Concurrent Dense + BM25 search, 
    RRF Fusion, Deduplication, Cross-Encoder Reranking, and Neighbor Expansion.
    """
    logger.info("REQUEST_RECEIVED | request_id=- | query='%s'", question)
    question_processed = _preprocess_query(question)
    k = _compute_dynamic_top_k(question_processed)
    target_sources = _extract_target_sources(question_processed)
    
    if target_sources:
        k = max(k, 6)
        
    search_k = k * 2

    start_time = time.perf_counter()
    
    dense_docs = []
    bm25_docs = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        dense_future = executor.submit(_dense_search_pipeline, question_processed, search_k, target_sources)
        bm25_future = executor.submit(_search_bm25_fallback, question_processed, search_k, target_sources)
        
        try:
            dense_docs = dense_future.result(timeout=15.0)
        except Exception as e:
            logger.error("Dense search pipeline failed: %s", e)
            
        try:
            bm25_docs = bm25_future.result(timeout=15.0)
        except Exception as e:
            logger.error("BM25 search pipeline failed: %s", e)
            
    concurrent_latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info("CONCURRENT_SEARCH_COMPLETED | latency_ms=%.1f | dense_count=%d | bm25_count=%d", 
                concurrent_latency_ms, len(dense_docs), len(bm25_docs))

    # Fusion and deduplication
    fused_docs = _rrf_fuse(dense_docs, bm25_docs)
    
    if not fused_docs:
        logger.warning("FUSION_EMPTY | No documents returned from dense or bm25.")
        return []

    # Optional: Reranking
    logger.info("RERANK_STARTED | request_id=- | chunk_count=%d", len(fused_docs))
    rerank_start_time = time.perf_counter()
    try:
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info("RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d", rerank_latency_ms, len(reranked_docs))
        
        if reranked_docs:
            return _expand_neighbor_chunks(reranked_docs, max_docs=max(k, 4), allowed_sources=target_sources)
        return []
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        return fused_docs[:k]
