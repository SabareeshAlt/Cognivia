import re
import time
import logging
import threading
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Union, Set, Optional
from langchain_core.documents import Document

# Setup logger to match the parent module
logger = logging.getLogger(__name__)

# Adjacency map for fast local lookup (matching Milvus.py globals)
# These will refer to the global variables in Milvus.py when merged.
_adjacency_map = {}
_adjacency_map_lock = threading.Lock()

def _strip_overlap(text_a: str, text_b: str, min_overlap: int = 20) -> str:
    """
    Finds the overlap between the suffix of text_a and the prefix of text_b,
    and returns text_b with the overlapping prefix removed.
    Enforces a minimum overlap length to avoid coincidental matches.
    """
    if not text_a or not text_b:
        return text_b
        
    max_search = min(len(text_a), len(text_b), 500)
    if max_search < min_overlap:
        return text_b
        
    for i in range(max_search, min_overlap - 1, -1):
        if text_a.endswith(text_b[:i]):
            return text_b[i:]
            
    return text_b

def _deduplicate_and_strip_overlaps(docs: List[Document]) -> List[Document]:
    """
    Deduplicates a list of documents by (document_path, chunk_index).
    Sorts them, groups them by document, and strips the overlap between consecutive chunks.
    """
    if not docs:
        return []
        
    from collections import defaultdict
    
    grouped = defaultdict(list)
    seen = set()
    
    for doc in docs:
        meta = doc.metadata or {}
        doc_path = meta.get("document_path") or meta.get("source") or "unknown"
        chunk_idx = meta.get("chunk_index")
        
        if chunk_idx is None:
            grouped[doc_path].append(doc)
            continue
            
        key = (doc_path, chunk_idx)
        if key not in seen:
            seen.add(key)
            grouped[doc_path].append(doc)
            
    final_docs = []
    for doc_path, group in grouped.items():
        # Sort chunks in this group by chunk_index
        group.sort(key=lambda x: x.metadata.get("chunk_index") if x.metadata.get("chunk_index") is not None else -1)
        
        if not group:
            continue
            
        # The first chunk doesn't need overlap stripping
        stripped_group = [
            Document(page_content=group[0].page_content, metadata=dict(group[0].metadata or {}))
        ]
        
        for i in range(1, len(group)):
            prev_doc = stripped_group[-1]
            curr_doc = group[i]
            
            prev_chunk_idx = prev_doc.metadata.get("chunk_index")
            curr_chunk_idx = curr_doc.metadata.get("chunk_index")
            
            # Only strip overlap if they are consecutive chunks in the same document
            if (prev_chunk_idx is not None and curr_chunk_idx is not None 
                    and curr_chunk_idx == prev_chunk_idx + 1):
                stripped_content = _strip_overlap(prev_doc.page_content, curr_doc.page_content)
                stripped_group.append(
                    Document(page_content=stripped_content, metadata=dict(curr_doc.metadata or {}))
                )
            else:
                stripped_group.append(
                    Document(page_content=curr_doc.page_content, metadata=dict(curr_doc.metadata or {}))
                )
                
        final_docs.extend(stripped_group)
        
    return final_docs

def _build_adjacency_map(corpus):
    """
    Build adjacency map based on document_path and chunk_index.
    """
    local_map = {}
    for doc in corpus:
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        chunk_index = metadata.get("chunk_index")
        if document_path and isinstance(chunk_index, int):
            local_map[(document_path, chunk_index)] = doc
            
    with _adjacency_map_lock:
        global _adjacency_map
        _adjacency_map = local_map

def _expand_neighbor_chunks(doc: Document, milvus_client=None, collection_name: str = None) -> List[Document]:
    """
    Query Milvus or local adjacency map for neighboring chunks (i-1 and i+1) based on metadata filtering.
    """
    metadata = doc.metadata or {}
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    document_path = metadata.get("document_path")
    
    if chunk_index is None:
        return [doc]
        
    target_indices = [chunk_index - 1, chunk_index + 1]
    target_indices = [i for i in target_indices if i >= 0]
    
    if not target_indices:
        return [doc]
        
    neighbors = []
    
    # 1. Try local adjacency map first
    global _adjacency_map
    if not _adjacency_map:
        # Import fallback functions from the local namespace of Milvus.py
        # These are accessible within Milvus.py where this code will reside.
        try:
            corpus = _fallback_chunk_corpus()
            if corpus:
                _build_adjacency_map(corpus)
        except NameError:
            pass
            
    if _adjacency_map and document_path:
        for idx in target_indices:
            neighbor = _adjacency_map.get((document_path, idx))
            if neighbor:
                neighbors.append(neighbor)
                
    # 2. If neighbors not found locally and Milvus could be available, query Milvus
    if len(neighbors) < len(target_indices):
        client = milvus_client
        coll_name = collection_name
        
        if client is None:
            try:
                cfg = _get_cloud_config()
                if cfg and not (time.monotonic() < _cloud_circuit_breaker["bypass_until"]):
                    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=1.5)
                    coll_name = cfg.get("collection", COLLECTION_NAME)
                else:
                    cfg = _get_local_config()
                    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=1.5)
                    coll_name = cfg.get("collection", COLLECTION_NAME)
            except Exception as e:
                logger.debug("Failed to connect to Milvus for neighbor expansion: %s", e)
                
        if client is not None and coll_name is not None and source is not None:
            escaped_source = source.replace("\\", "\\\\").replace('"', '\\"')
            expr = f'source == "{escaped_source}" and chunk_index in {target_indices}'
            
            try:
                output_fields = ["text"] + list(metadata.keys())
                results = client.query(
                    collection_name=coll_name,
                    filter=expr,
                    output_fields=output_fields
                )
                
                milvus_neighbors = []
                for res in results:
                    text = res.pop("text", "")
                    res.pop("pk", None)
                    res.pop("vector", None)
                    milvus_neighbors.append(Document(page_content=text, metadata=res))
                    
                existing_indices = {n.metadata.get("chunk_index") for n in neighbors}
                for n in milvus_neighbors:
                    idx = n.metadata.get("chunk_index")
                    if idx not in existing_indices:
                        neighbors.append(n)
                        existing_indices.add(idx)
            except Exception as e:
                logger.warning("Failed to expand neighbor chunks via Milvus for %s (index %s): %s", source, chunk_index, e)
                
    all_docs = [doc] + neighbors
    all_docs.sort(key=lambda x: x.metadata.get("chunk_index", 0))
    
    return all_docs

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
    
    dense_failed = False
    dense_timeout = False
    
    executor = ThreadPoolExecutor(max_workers=2)
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
    logger.info("CONCURRENT_SEARCH_COMPLETED | latency_ms=%.1f | dense_count=%d | bm25_count=%d", 
                concurrent_latency_ms, len(dense_docs), len(bm25_docs))

    # Detailed retrieval stats logging
    total_retrieval_latency_ms = concurrent_latency_ms
    fallback_triggered = len(dense_docs) == 0 or dense_failed
    logger.info("RETRIEVAL_STATS | total_retrieval_latency_ms=%.1f | timeout_triggered=%s | fallback_triggered=%s",
                total_retrieval_latency_ms, dense_timeout, fallback_triggered)

    # Fusion and deduplication
    fused_docs = _rrf_fuse(dense_docs, bm25_docs, search_k)
    
    if not fused_docs:
        logger.warning("FUSION_EMPTY | No documents returned from dense or bm25.")
        return []

    # Optional: Reranking
    logger.info("RERANK_STARTED | request_id=- | chunk_count=%d", len(fused_docs))
    rerank_start_time = time.perf_counter()
    
    primary_docs = []
    try:
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info("RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d", rerank_latency_ms, len(reranked_docs))
        
        if reranked_docs:
            primary_docs = reranked_docs[:max(k, 4)]
        else:
            primary_docs = fused_docs[:k]
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        primary_docs = fused_docs[:k]

    # Expand neighbor chunks for continuity
    expanded_docs = []
    for doc in primary_docs:
        expanded_docs.extend(_expand_neighbor_chunks(doc))
        
    # Deduplicate and strip overlaps
    final_docs = _deduplicate_and_strip_overlaps(expanded_docs)
    
    return final_docs

def _format_context(docs, max_chars=32000):
    """
    Formats the context for the LLM. 
    1. Increases capacity limit to 32000 (equivalent token-safe limit).
    2. Chronologically sorts the chunks by (source, page_number, chunk_index)
       before formatting to preserve document flow.
    """
    def get_sort_key(doc):
        meta = doc.metadata or {}
        # Ensure source is string for comparison
        source = str(meta.get("source", ""))
        
        # Ensure page_number is int for comparison
        page_num = meta.get("page_number")
        if page_num is None:
            page_num = 0
        else:
            try:
                page_num = int(page_num)
            except (ValueError, TypeError):
                page_num = 0
                
        # Ensure chunk_index is int for comparison
        chunk_idx = meta.get("chunk_index")
        if chunk_idx is None:
            chunk_idx = 0
        else:
            try:
                chunk_idx = int(chunk_idx)
            except (ValueError, TypeError):
                chunk_idx = 0
                
        return (source, page_num, chunk_idx)

    # Sort retrieved chunks chronologically before formatting
    sorted_docs = sorted(docs, key=get_sort_key)
    
    max_tokens = max_chars // 4
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoder = None

    formatted = []
    
    if encoder:
        current_tokens = 0
        for doc in sorted_docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = doc.page_content
            
            header_tokens = len(encoder.encode(chunk_header))
            content_tokens = len(encoder.encode(content))
            total_chunk_tokens = header_tokens + content_tokens
            
            if current_tokens + total_chunk_tokens > max_tokens:
                remaining_tokens = max_tokens - current_tokens - header_tokens
                if remaining_tokens > 20:
                    encoded = encoder.encode(content)
                    truncated_content = encoder.decode(encoded[:remaining_tokens])
                    # Ensure sentence boundary truncation
                    match = list(re.finditer(r'[.!?]\s+', truncated_content))
                    if match:
                        truncated_content = truncated_content[:match[-1].end()].strip()
                    formatted.append(chunk_header + truncated_content + " ... [TRUNCATED]")
                break
            
            formatted.append(chunk_header + content)
            current_tokens += total_chunk_tokens
            
    else:
        current_chars = 0
        for doc in sorted_docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = doc.page_content
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
