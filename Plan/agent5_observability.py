# Plan/agent5_observability.py
# Observability & Debugging implementation plan and logging-enhanced functions.
# This file is prepared for Coordinator Agent / main agent to merge into Milvus.py and rag/llm_orchestration.py.

import logging
import time
import re
import json
from typing import List, Tuple, Optional, Any, Set, Union
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# =====================================================================
# 1. ENHANCEMENTS FOR Milvus.py
# =====================================================================

def _search_milvus_with_config(cfg: dict, question: str, k: int, target_sources: set[str] | None, timeout_sec: float) -> list[Document]:
    """
    Enhanced version of _search_milvus_with_config to capture and store 
    vector similarity score in document metadata.
    """
    if not cfg:
        return []
    source_expr = _milvus_source_filter_expr(target_sources or set())
    embeddings = OllamaEmbeddings(model=cfg["model"], base_url=OLLAMA_BASE_URL)
    query_vector = embeddings.embed_query(question)
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=timeout_sec)
    search_kwargs = {
        "collection_name": cfg["collection"],
        "data": [query_vector],
        "anns_field": "vector",
        "search_params": {"metric_type": "COSINE", "params": {}},
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
            logger.warning("Milvus collection '%s' does not exist; returning empty list. Error: %s", cfg["collection"], e)
            return []
        raise e
    hits = rows[0] if rows else []
    docs = []
    for hit in hits:
        if isinstance(hit, dict):
            entity = hit.get("entity") or {}
            score = hit.get("distance")
        else:
            entity = getattr(hit, "entity", {}) or {}
            score = getattr(hit, "score", None) or getattr(hit, "distance", None)
        text = str(entity.get("text") or "")
        if not text:
            continue
        metadata = {key: value for key, value in entity.items() if key != "text"}
        
        # Capture and store vector similarity score (Cosine distance/similarity)
        if score is not None:
            metadata["vector_score"] = float(score)
            
        docs.append(Document(page_content=text, metadata=metadata))
    return _filter_docs_by_sources(docs, target_sources or set())


def _fallback_retrieve_docs(question: str, k: int, target_sources: set[str] | None = None) -> list[Document]:
    """
    Enhanced version of _fallback_retrieve_docs to explicitly tag 
    lexical (BM25) score in document metadata.
    """
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
            # Capture and store BM25 score and combined fallback score in metadata
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={
                    **doc.metadata, 
                    "score": score,
                    "bm25_score": lexical_score,
                    "combined_fallback_score": score
                }
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


def _expand_neighbor_chunks(doc: Document, milvus_client, collection_name: str) -> List[Document]:
    """
    Enhanced version of _expand_neighbor_chunks to log neighborhood expansion and
    tag the neighbors with is_neighbor metadata so it can be tracked in the Context Layer.
    """
    metadata = doc.metadata or {}
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    
    if source is None or chunk_index is None:
        return [doc]
        
    target_indices = [chunk_index - 1, chunk_index + 1]
    target_indices = [i for i in target_indices if i >= 0]
    
    if not target_indices:
        return [doc]
        
    escaped_source = source.replace("\\", "\\\\").replace('"', '\\"')
    expr = f'source == "{escaped_source}" and chunk_index in {target_indices}'
    
    try:
        output_fields = ["text"] + list(metadata.keys())
        results = milvus_client.query(
            collection_name=collection_name,
            filter=expr,
            output_fields=output_fields
        )
        
        neighbors = []
        for res in results:
            text = res.pop("text", "")
            res.pop("pk", None)
            res.pop("vector", None)
            # Tag neighbor document so the Context Layer log can identify it
            res["is_neighbor"] = True
            neighbors.append(Document(page_content=text, metadata=res))
            
        all_docs = [doc] + neighbors
        all_docs.sort(key=lambda x: x.metadata.get("chunk_index", 0))
        
        # Log neighborhood expansion
        logger.info(
            "CONTEXT_LAYER | neighbor_expansion | source='%s' | chunk_index=%s | neighbors_added=%d", 
            source, chunk_index, len(neighbors)
        )
        
        return all_docs
        
    except Exception as e:
        logger.warning("Failed to expand neighbor chunks for %s (index %s): %s", source, chunk_index, e)
        return [doc]


def _augment_docs_for_syllabus(question: str, docs: list[Document]) -> list[Document]:
    """
    Enhanced version of _augment_docs_for_syllabus to tag augmented/expanded docs 
    with is_augmented metadata so it can be tracked in the Context Layer.
    """
    if not _is_syllabus_query(question) or not docs:
        return docs
    corpus = _fallback_chunk_corpus()
    by_page: dict[tuple[object, object], Document] = {}
    for doc in corpus:
        key = ((doc.metadata or {}).get('document_path'), (doc.metadata or {}).get('page_number'))
        existing = by_page.get(key)
        if existing is None:
            by_page[key] = doc
            continue
        current_index = int((doc.metadata or {}).get('chunk_index') or 0)
        existing_index = int((existing.metadata or {}).get('chunk_index') or 0)
        if current_index < existing_index:
            by_page[key] = doc
    augmented = list(docs)
    seen = {((doc.metadata or {}).get('document_path'), (doc.metadata or {}).get('page_number'), (doc.metadata or {}).get('chunk_index')) for doc in docs}
    augmented_count = 0
    for doc in docs:
        page_number = (doc.metadata or {}).get('page_number')
        document_path = (doc.metadata or {}).get('document_path')
        if not document_path or not isinstance(page_number, int):
            continue
        if _explicit_unit_title_line_count(doc.page_content) < 1:
            continue
        next_doc = by_page.get((document_path, page_number + 1))
        if not next_doc:
            continue
        next_key = ((next_doc.metadata or {}).get('document_path'), (next_doc.metadata or {}).get('page_number'), (next_doc.metadata or {}).get('chunk_index'))
        if next_key not in seen:
            # Create a shallow copy and tag it as augmented
            augmented_doc = Document(
                page_content=next_doc.page_content,
                metadata={**next_doc.metadata, "is_augmented": True}
            )
            augmented.append(augmented_doc)
            seen.add(next_key)
            augmented_count += 1
            
    if augmented_count > 0:
        logger.info(
            "CONTEXT_LAYER | syllabus_augmentation | queries='%s' | augmented_chunks_added=%d", 
            question.replace('\n', ' '), augmented_count
        )
    return augmented


def _retrieve_docs(question: str) -> list:
    """
    Enhanced version of _retrieve_docs orchestrating:
      1. Query Layer logging (incoming, preprocessed queries)
      2. Retrieval Layer logging (retrieved dense, sparse, reranked, and selected chunks with scores)
    """
    logger.info("REQUEST_RECEIVED | request_id=- | query='%s'", question)
    question_processed = _preprocess_query(question)
    
    # 1. Query Layer Logging
    logger.info(
        "QUERY_LAYER | incoming_query='%s' | rewritten_query='%s'",
        question.replace('\n', ' '), 
        question_processed.replace('\n', ' ')
    )
    
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

    # 2. Retrieval Layer Logging - Retrieved Chunks before fusion/filtering
    for idx, doc in enumerate(dense_docs):
        meta = doc.metadata or {}
        logger.info(
            "RETRIEVAL_LAYER | type=DENSE | rank=%d | source='%s' | page=%s | chunk_idx=%s | vector_score=%s | snippet='%s...'",
            idx + 1,
            meta.get("source"),
            meta.get("page_number"),
            meta.get("chunk_index"),
            meta.get("vector_score", "N/A"),
            doc.page_content[:100].replace('\n', ' ')
        )

    for idx, doc in enumerate(bm25_docs):
        meta = doc.metadata or {}
        logger.info(
            "RETRIEVAL_LAYER | type=BM25 | rank=%d | source='%s' | page=%s | chunk_idx=%s | bm25_score=%s | combined_fallback_score=%s | snippet='%s...'",
            idx + 1,
            meta.get("source"),
            meta.get("page_number"),
            meta.get("chunk_index"),
            meta.get("bm25_score", "N/A"),
            meta.get("score", "N/A"),
            doc.page_content[:100].replace('\n', ' ')
        )

    # Fusion and deduplication
    fused_docs = _rrf_fuse(dense_docs, bm25_docs, search_k)
    
    if not fused_docs:
        logger.warning("FUSION_EMPTY | No documents returned from dense or bm25.")
        return []

    # Optional: Reranking
    logger.info("RERANK_STARTED | request_id=- | chunk_count=%d", len(fused_docs))
    rerank_start_time = time.perf_counter()
    selected_docs = []
    try:
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info("RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d", rerank_latency_ms, len(reranked_docs))
        
        # Log Reranker Scores
        for idx, doc in enumerate(reranked_docs):
            meta = doc.metadata or {}
            logger.info(
                "RETRIEVAL_LAYER | type=RERANKED | rank=%d | source='%s' | page=%s | chunk_idx=%s | rerank_score=%s | snippet='%s...'",
                idx + 1,
                meta.get("source"),
                meta.get("page_number"),
                meta.get("chunk_index"),
                meta.get("rerank_score", "N/A"),
                doc.page_content[:100].replace('\n', ' ')
            )
            
        if reranked_docs:
            selected_docs = reranked_docs[:max(k, 4)]
        else:
            selected_docs = fused_docs[:k]
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        selected_docs = fused_docs[:k]

    # Log the final Selected Chunks
    for idx, doc in enumerate(selected_docs):
        meta = doc.metadata or {}
        logger.info(
            "RETRIEVAL_LAYER | type=SELECTED | rank=%d | source='%s' | page=%s | chunk_idx=%s | rrf_score=%s | rerank_score=%s | snippet='%s...'",
            idx + 1,
            meta.get("source"),
            meta.get("page_number"),
            meta.get("chunk_index"),
            meta.get("rrf_score", "N/A"),
            meta.get("rerank_score", "N/A"),
            doc.page_content[:100].replace('\n', ' ')
        )

    return selected_docs


def _format_context(docs, max_chars=4000):
    """
    Enhanced version of _format_context to track and log:
      - Context character count
      - Context token count (using tiktoken or heuristic)
      - Dropped chunks count (chunks that were skipped because of limit)
      - Neighbor expansion count (identified using metadata flags)
    """
    max_tokens = max_chars // 4
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoder = None

    formatted = []
    total_docs = len(docs)
    dropped_chunks_count = 0
    
    if encoder:
        current_tokens = 0
        for i, doc in enumerate(docs):
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
                    dropped_chunks_count = total_docs - i - 1
                else:
                    dropped_chunks_count = total_docs - i
                break
            
            formatted.append(chunk_header + content)
            current_tokens += total_chunk_tokens
            
    else:
        current_chars = 0
        for i, doc in enumerate(docs):
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
                    dropped_chunks_count = total_docs - i - 1
                else:
                    dropped_chunks_count = total_docs - i
                break
                
            formatted.append(chunk_text)
            current_chars += len(chunk_text) + 2
            
    final_context = "\n\n".join(formatted)
    final_char_count = len(final_context)
    
    if encoder:
        final_token_count = len(encoder.encode(final_context))
    else:
        final_token_count = final_char_count // 4

    # Track neighbor expansion count in the current context
    neighbor_expansion_count = sum(
        1 for doc in docs 
        if (doc.metadata or {}).get("is_neighbor") or (doc.metadata or {}).get("is_augmented")
    )
    
    # 3. Context Layer Logging
    logger.info(
        "CONTEXT_LAYER | final_context_token_count=%d | final_context_char_count=%d | dropped_chunks_count=%d | neighbor_expansion_count=%d",
        final_token_count,
        final_char_count,
        dropped_chunks_count,
        neighbor_expansion_count
    )
    
    return final_context


# =====================================================================
# 2. ENHANCEMENTS FOR rag/llm_orchestration.py
# =====================================================================

def _invoke_with_provider_failover(context: str, question: str) -> str:
    """
    Enhanced version of _invoke_with_provider_failover to capture and log:
      - Selected model, provider routing decisions (Groq vs Ollama)
      - LLM latency
      - Raw LLM output
      - Fallback trigger reason (if a failure/fallback occurs)
    """
    prompt = _build_qa_chain()
    payload = {"context": context, "question": question}
    failures = []
    start_time = time.perf_counter()

    providers = _preferred_llm_providers()
    
    # Log the routing decision (Generation Layer)
    logger.info("GENERATION_LAYER | routing_decision=%s | preferred_providers=%s | model='%s'", 
                LLM_PROVIDER, providers, LLM_MODEL)

    for index, provider in enumerate(providers):
        provider_start_time = time.perf_counter()
        try:
            llm = _create_llm_client(provider)
            chain = prompt | llm | StrOutputParser()
            
            response = chain.invoke(payload)
            
            latency_ms = (time.perf_counter() - provider_start_time) * 1000
            
            # Log successful generation (Generation Layer)
            logger.info(
                "GENERATION_LAYER | status=SUCCESS | provider='%s' | model='%s' | latency_ms=%.1f | raw_output='%s'",
                provider,
                LLM_MODEL,
                latency_ms,
                response.replace('\n', ' ')
            )
            
            circuit_breaker.record_success(provider)
            return response
        except Exception as exc:
            latency_ms = (time.perf_counter() - provider_start_time) * 1000
            failures.append((provider, str(exc)))
            circuit_breaker.record_failure(provider)
            
            # Log fallback/failover trigger reason (Generation Layer)
            logger.warning(
                "GENERATION_LAYER | status=FAILOVER_TRIGGERED | provider='%s' | model='%s' | latency_ms=%.1f | error='%s'",
                provider,
                LLM_MODEL,
                latency_ms,
                str(exc)
            )
            logger.warning("LLM provider '%s' failed; trying fallback. Error: %s", provider, exc)

    details = "; ".join(f"{provider}={error}" for provider, error in failures) or "unknown error"
    logger.error("GENERATION_LAYER | status=ALL_FAILED | details='%s'", details)
    raise RuntimeError(f"All LLM providers failed: {details}")


def _stream_with_provider_failover(context: str, question: str):
    """
    Enhanced version of _stream_with_provider_failover to capture and log:
      - Selected model, provider routing decisions (Groq vs Ollama)
      - Stream TTFT & Latency
      - Raw LLM output
      - Fallback trigger reason (if a failure/fallback occurs)
    """
    prompt = _build_qa_chain()
    payload = {"context": context, "question": question}
    providers = _preferred_llm_providers()
    failures = []
    start_time = time.perf_counter()

    # Log the routing decision (Generation Layer)
    logger.info("GENERATION_LAYER | status=STREAM_START | routing_decision=%s | preferred_providers=%s | model='%s'", 
                LLM_PROVIDER, providers, LLM_MODEL)

    for index, provider in enumerate(providers):
        provider_start_time = time.perf_counter()
        emitted = False
        try:
            llm = _create_llm_client(provider)
            chain = prompt | llm | StrOutputParser()
            
            token_count = 0
            first_token_time = None
            raw_output_chunks = []
            
            for chunk in chain.stream(payload):
                if not emitted:
                    first_token_time = time.perf_counter()
                    ttft_ms = (first_token_time - provider_start_time) * 1000
                    logger.info(f"TTFT (Time To First Token) via {provider}: {ttft_ms:.1f}ms")
                    # Log TTFT (Generation Layer)
                    logger.info("GENERATION_LAYER | status=STREAM_TTFT | provider='%s' | ttft_ms=%.1f", provider, ttft_ms)
                emitted = True
                token_count += 1
                raw_output_chunks.append(chunk)
                yield chunk
                
            if emitted:
                total_time = time.perf_counter() - provider_start_time
                total_time_ms = total_time * 1000
                raw_output = "".join(raw_output_chunks)
                if first_token_time:
                    gen_time = time.perf_counter() - first_token_time
                    tps = token_count / gen_time if gen_time > 0 else 0
                    logger.info(f"Generation completed via {provider}. Tokens/sec: {tps:.1f}")
                
                # Log successful streaming completion (Generation Layer)
                logger.info(
                    "GENERATION_LAYER | status=SUCCESS | type=STREAM | provider='%s' | model='%s' | latency_ms=%.1f | raw_output='%s'",
                    provider,
                    LLM_MODEL,
                    total_time_ms,
                    raw_output.replace('\n', ' ')
                )
                
            circuit_breaker.record_success(provider)
            return
        except Exception as exc:
            latency_ms = (time.perf_counter() - provider_start_time) * 1000
            failures.append((provider, str(exc)))
            circuit_breaker.record_failure(provider)
            can_fallback = index < len(providers) - 1 and not emitted
            
            # Log failover/fallback trigger reason (Generation Layer)
            logger.warning(
                "GENERATION_LAYER | status=FAILOVER_TRIGGERED | type=STREAM | provider='%s' | model='%s' | latency_ms=%.1f | error='%s' | can_fallback=%s",
                provider,
                LLM_MODEL,
                latency_ms,
                str(exc),
                can_fallback
            )
            if can_fallback:
                logger.warning(
                    "Streaming LLM provider '%s' failed before output; trying fallback. Error: %s",
                    provider,
                    exc,
                )
                continue
            logger.error("Streaming LLM provider '%s' failed: %s", provider, exc)
            raise

    details = "; ".join(f"{provider}={error}" for provider, error in failures) or "unknown error"
    logger.error("GENERATION_LAYER | status=ALL_STREAM_FAILED | details='%s'", details)
    raise RuntimeError(f"All streaming LLM providers failed: {details}")
