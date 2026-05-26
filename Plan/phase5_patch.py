import re
import sys

def apply_phase5_patch():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Query Cache
    cache_code = r"""
_query_cache = {}
_query_cache_lock = threading.Lock()
QUERY_CACHE_TTL = 300  # 5 minutes

def _get_cached_query(question: str):
    with _query_cache_lock:
        if question in _query_cache:
            timestamp, response = _query_cache[question]
            if time.monotonic() - timestamp < QUERY_CACHE_TTL:
                return response
            del _query_cache[question]
    return None

def _set_cached_query(question: str, response: str):
    with _query_cache_lock:
        _query_cache[question] = (time.monotonic(), response)

def get_optimized_response(question: str) -> str:
    cached = _get_cached_query(question)
    if cached:
        logger.info("Serving response from TTL cache.")
        return cached

    syllabus_text = _extract_syllabus_text(question)
    if syllabus_text:
        _set_cached_query(question, syllabus_text)
        return syllabus_text

    docs = _augment_docs_for_syllabus(question, _retrieve_docs(question))
    if not docs:
        _set_cached_query(question, INSUFFICIENT_CONTEXT_MESSAGE)
        return INSUFFICIENT_CONTEXT_MESSAGE

    context = _format_context(docs)
    response = _invoke_with_provider_failover(context=context, question=question)
    _set_cached_query(question, response)
    return response
"""
    # Replace get_optimized_response
    content = re.sub(r'def get_optimized_response\(question: str\) -> str:.*?(?=\ndef stream_optimized_response)', lambda m: cache_code, content, flags=re.DOTALL)

    # 2. Persist BM25 Index
    bm25_persist_code = r"""
import pickle

BM25_INDEX_FILE = os.path.join(PROJECT_ROOT, "bm25_index.pkl")

def _refresh_fallback_cache() -> None:
    file_metadata = _collect_pdf_metadata()
    docs = tuple(_load_and_chunk_files(file_metadata))
    stats = _build_fallback_stats_from_docs(docs)
    signature = _fallback_signature(file_metadata)
    
    with _fallback_cache_lock:
        _fallback_cache_state["corpus"] = docs
        _fallback_cache_state["stats"] = stats
        _fallback_cache_state["signature"] = signature
        _fallback_cache_state["inflight"] = False

    try:
        with open(BM25_INDEX_FILE, "wb") as f:
            pickle.dump({
                "signature": signature,
                "corpus": docs,
                "stats": stats
            }, f)
    except Exception as e:
        logger.warning(f"Failed to persist BM25 index: {e}")

def _load_persisted_bm25() -> bool:
    if not os.path.exists(BM25_INDEX_FILE):
        return False
    try:
        with open(BM25_INDEX_FILE, "rb") as f:
            data = pickle.load(f)
            
        current_sig = _fallback_signature(_collect_pdf_metadata())
        if data["signature"] == current_sig:
            with _fallback_cache_lock:
                _fallback_cache_state["corpus"] = data["corpus"]
                _fallback_cache_state["stats"] = data["stats"]
                _fallback_cache_state["signature"] = data["signature"]
                _fallback_cache_state["inflight"] = False
            return True
    except Exception as e:
        logger.warning(f"Failed to load persisted BM25 index: {e}")
    return False

def _fallback_chunk_corpus() -> tuple[Document, ...]:
    file_metadata = _collect_pdf_metadata()
    signature = _fallback_signature(file_metadata)
    with _fallback_cache_lock:
        cached_signature = _fallback_cache_state["signature"]
        cached_corpus = _fallback_cache_state["corpus"]
        has_cache = bool(cached_corpus)
        
    if cached_signature != signature:
        if not _load_persisted_bm25():
            _schedule_fallback_cache_refresh(force=True)
            
    if has_cache:
        return cached_corpus
        
    _wait_for_fallback_cache()
    
    with _fallback_cache_lock:
        return _fallback_cache_state["corpus"] or tuple()
"""
    content = re.sub(r'def _refresh_fallback_cache\(\) -> None:.*?(?=\ndef _fallback_corpus_stats)', lambda m: bm25_persist_code, content, flags=re.DOTALL)

    # 3. Chunk Adjacency Map
    adjacency_code = r"""
_adjacency_map = {}
_adjacency_map_lock = threading.Lock()

def _build_adjacency_map(corpus):
    local_map = {}
    for doc in corpus:
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        page_number = metadata.get("page_number")
        chunk_index = metadata.get("chunk_index")
        if document_path and isinstance(page_number, int) and isinstance(chunk_index, int):
            local_map[(document_path, page_number, chunk_index)] = doc
            
    with _adjacency_map_lock:
        global _adjacency_map
        _adjacency_map = local_map

def _expand_neighbor_chunks(docs: list[Document], max_docs: int, allowed_sources: set[str] | None = None) -> list[Document]:
    if not docs:
        return docs

    corpus = _fallback_chunk_corpus()
    
    with _adjacency_map_lock:
        if not _adjacency_map or len(_adjacency_map) != len(corpus):
            _build_adjacency_map(corpus)
        index_by_key = _adjacency_map

    allowed = {source.lower() for source in (allowed_sources or set())}
    expanded = list(docs)
    seen = set()
    
    for doc in docs:
        metadata = doc.metadata or {}
        key = (
            metadata.get("document_path"),
            metadata.get("page_number"),
            metadata.get("chunk_index")
        )
        seen.add(key)

    for doc in docs:
        if len(expanded) >= max_docs:
            break
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        page_number = metadata.get("page_number")
        chunk_index = metadata.get("chunk_index")
        
        if not document_path or not isinstance(page_number, int) or not isinstance(chunk_index, int):
            continue
            
        for neighbor_chunk_index in (chunk_index - 1, chunk_index + 1):
            key = (document_path, page_number, neighbor_chunk_index)
            neighbor = index_by_key.get(key)
            if neighbor and key not in seen:
                if allowed and _doc_source(neighbor).lower() not in allowed:
                    continue
                expanded.append(neighbor)
                seen.add(key)
                if len(expanded) >= max_docs:
                    break

    return expanded[:max_docs]
"""
    content = re.sub(r'def _expand_neighbor_chunks.*?return expanded\[:max_docs\]', lambda m: adjacency_code, content, flags=re.DOTALL)

    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    apply_phase5_patch()
    print("Phase 5 patch applied successfully.")
