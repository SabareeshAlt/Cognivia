import os
import re
import math
import logging
import time
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from typing import Optional, Any, List, Tuple, Union, Set
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from pymilvus import DataType, FieldSchema, CollectionSchema, MilvusClient

logger = logging.getLogger(__name__)

# Standardize embedding model and dimension properties
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIMENSION = 768

# Reference placeholders from Milvus.py context
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
RELEVANCE_SCORE_THRESHOLD = float(os.getenv("ACADEMERAG_SCORE_THRESHOLD", "0.35"))
BM25_K1 = 1.5
BM25_B = 0.75
INGEST_BATCH_SIZE = 16
INGEST_MAX_SECONDS = 1800.0
MILVUS_INIT_TIMEOUT_SECONDS = 10.0
STOPWORDS = {
    "a", "an", "and", "are", "for", "from", "in", "is", "of", "on", "or", "the",
    "to", "what", "which", "with", "each", "tell", "me"
}

def _is_zero_vector(vector: List[float]) -> bool:
    """Helper validation to reject zero-vectors."""
    if not vector:
        return True
    return all(v == 0.0 for v in vector) or sum(x * x for x in vector) < 1e-9

def _verify_collection_dimension_and_rebuild(cfg: dict, client: Optional[MilvusClient] = None) -> bool:
    """
    Verifies that the existing collection has dimension 768.
    If it doesn't match or cannot be queried, triggers a forced rebuild.
    Returns True if the check passes without rebuilding, False if a rebuild was triggered.
    """
    # Import locally to avoid circular dependencies
    from Milvus import initialize_vector_store
    
    if client is None:
        client = MilvusClient(uri=cfg["uri"], token=cfg["token"])
        
    if not client.has_collection(cfg["collection"]):
        return True # Schema creation will handle it
    
    dim = None
    try:
        desc = client.describe_collection(cfg["collection"])
        schema = desc.get("schema", {})
        fields = schema.get("fields", []) if isinstance(schema, dict) else getattr(schema, "fields", [])
        for field in fields:
            field_name = field.get("name") if isinstance(field, dict) else getattr(field, "name", None)
            if field_name == "vector":
                params = field.get("params", {}) if isinstance(field, dict) else getattr(field, "params", {})
                dim = params.get("dim") if isinstance(params, dict) else getattr(params, "get", lambda k: None)("dim")
                if dim is None:
                    dim = field.get("dim") if isinstance(field, dict) else getattr(field, "dim", None)
                break
    except Exception as e:
        logger.warning(f"Could not describe collection schema to verify dimension: {e}")
        
    if dim is None:
        try:
            res = client.query(collection_name=cfg["collection"], filter="pk >= 0", output_fields=["vector"], limit=1)
            if res and "vector" in res[0]:
                dim = len(res[0]["vector"])
        except Exception as e:
            logger.warning(f"Could not query sample vector to verify dimension: {e}")
            
    if dim is not None and dim != EMBEDDING_DIMENSION:
        logger.warning(f"Collection dimension mismatch: expected {EMBEDDING_DIMENSION}, found {dim}. Triggering forced rebuild.")
        initialize_vector_store(force_reindex=True, recreate_collection_on_sync=True, allow_background_sync=False)
        return False
    return True

# --- MODIFIED FUNCTIONS FOR MILVUS.PY ---

def ensure_collection_schema(cfg: dict, embeddings, recreate: bool = False) -> bool:
    """
    Ensure collection exists with explicit schema before ingestion.
    Forces dimension size to 768 and triggers rebuild on dimension mismatch.
    """
    from Milvus import _connect_milvus_client, _wait_for_collection_absence, _wait_for_collection_presence
    
    client = _connect_milvus_client(cfg)
    exists = client.has_collection(cfg["collection"])

    if exists and recreate:
        logger.info("Dropping existing Milvus collection: %s", cfg["collection"])
        client.drop_collection(cfg["collection"])
        _wait_for_collection_absence(client, cfg["collection"])
        exists = False

    if exists:
        # Check existing collection's dimension to ensure it is 768
        dim = None
        try:
            desc = client.describe_collection(cfg["collection"])
            schema = desc.get("schema", {})
            fields = schema.get("fields", []) if isinstance(schema, dict) else getattr(schema, "fields", [])
            for field in fields:
                field_name = field.get("name") if isinstance(field, dict) else getattr(field, "name", None)
                if field_name == "vector":
                    params = field.get("params", {}) if isinstance(field, dict) else getattr(field, "params", {})
                    dim = params.get("dim") if isinstance(params, dict) else getattr(params, "get", lambda k: None)("dim")
                    if dim is None:
                        dim = field.get("dim") if isinstance(field, dict) else getattr(field, "dim", None)
                    break
        except Exception as e:
            logger.warning(f"Could not describe collection schema inside ensure_collection_schema: {e}")
            
        if dim is not None and dim != EMBEDDING_DIMENSION:
            logger.warning(f"Dimension mismatch inside ensure_collection_schema: expected {EMBEDDING_DIMENSION}, found {dim}. Triggering recreation.")
            client.drop_collection(cfg["collection"])
            _wait_for_collection_absence(client, cfg["collection"])
            exists = False
        else:
            return True

    dim = EMBEDDING_DIMENSION
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

    # Add scalar indexes for optimized metadata filtering.
    scalar_index_params = MilvusClient.prepare_index_params()
    scalar_index_params.add_index(field_name="source", index_name="source_idx")
    scalar_index_params.add_index(field_name="page_number", index_name="page_number_idx")
    scalar_index_params.add_index(field_name="chunk_index", index_name="chunk_index_idx")
    
    client.create_index(collection_name=cfg["collection"], index_params=scalar_index_params)
    
    return True


def _ingest_documents_with_client(cfg: dict, embeddings, docs) -> None:
    """
    Ingest document chunks directly using pymilvus client interface.
    Validates embeddings dimensions and rejects zero-vectors.
    """
    from Milvus import _connect_milvus_client_with_timeout, initialize_vector_store
    
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=MILVUS_INIT_TIMEOUT_SECONDS)
    
    # Check collection dimension before inserting
    _verify_collection_dimension_and_rebuild(cfg, client)
    
    total = len(docs)
    start = time.monotonic()
    logger.info(
        "Starting Milvus client ingestion for %s chunk(s) with batch size %s (timeout %.0fs).",
        total,
        INGEST_BATCH_SIZE,
        INGEST_MAX_SECONDS,
    )
    for offset in range(0, total, INGEST_BATCH_SIZE):
        elapsed = time.monotonic() - start
        if elapsed > INGEST_MAX_SECONDS:
            raise TimeoutError(
                f"Ingestion timed out after {elapsed:.1f}s (limit {INGEST_MAX_SECONDS:.1f}s)"
            )
        batch = docs[offset : offset + INGEST_BATCH_SIZE]
        batch_texts = [doc.page_content for doc in batch]
        batch_vectors = embeddings.embed_documents(batch_texts)
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"Embedding size mismatch: got {len(batch_vectors)} vectors for {len(batch)} chunks"
            )
        
        payload = []
        for doc, vector in zip(batch, batch_vectors):
            if len(vector) != EMBEDDING_DIMENSION:
                logger.warning(f"Embedding dimension mismatch during insert: expected {EMBEDDING_DIMENSION}, got {len(vector)}. Rebuilding index.")
                initialize_vector_store(force_reindex=True, recreate_collection_on_sync=True, allow_background_sync=False)
                raise ValueError(f"Vector dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(vector)}")
            
            if _is_zero_vector(vector):
                logger.warning("Rejecting zero-vector during document ingestion. Chunk content: %s", doc.page_content[:100])
                continue # Reject zero-vector by skipping it

            meta = doc.metadata or {}
            row = {
                "text": doc.page_content, 
                "vector": vector,
                "source": str(meta.get("source", ""))[:1024],
                "page_number": int(meta.get("page_number", 0)),
                "chunk_index": int(meta.get("chunk_index", 0))
            }
            # Put remaining metadata fields into dynamic fields
            for k, v in meta.items():
                if k not in ["source", "page_number", "chunk_index"]:
                    row[k] = v
                    
            payload.append(row)
            
        batch_start = time.monotonic()
        if payload:
            client.insert(collection_name=cfg["collection"], data=payload)
        completed = min(offset + len(batch), total)
        percent = (completed / total) * 100.0
        batch_elapsed = time.monotonic() - batch_start
        avg_per_chunk = (time.monotonic() - start) / completed
        remaining_chunks = total - completed
        eta = remaining_chunks * avg_per_chunk
        logger.info(
            "Client ingestion progress: %s/%s chunks (%.1f%%) | batch %.2fs | elapsed %.1fs | eta %.1fs",
            completed,
            total,
            percent,
            batch_elapsed,
            time.monotonic() - start,
            eta,
        )
    logger.info("Milvus client ingestion completed in %.1fs.", time.monotonic() - start)


def _search_milvus_with_config(cfg: dict, question: str, k: int, target_sources: set[str] | None, timeout_sec: float) -> list[Document]:
    """
    Search Milvus using direct client queries.
    Performs dimension checks, zero-vector checks, dense similarity thresholding, and passes 'ef' param.
    """
    from Milvus import _milvus_source_filter_expr, _connect_milvus_client_with_timeout, _filter_docs_by_sources, initialize_vector_store
    
    if not cfg:
        return []
    source_expr = _milvus_source_filter_expr(target_sources or set())
    embeddings = OllamaEmbeddings(model=cfg["model"], base_url=OLLAMA_BASE_URL)
    query_vector = embeddings.embed_query(question)
    
    # Verify query vector dimension is 768
    if len(query_vector) != EMBEDDING_DIMENSION:
        logger.warning(f"Query vector dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(query_vector)}. Rebuilding index.")
        initialize_vector_store(force_reindex=True, recreate_collection_on_sync=True, allow_background_sync=False)
        # Re-fetch embeddings after rebuild
        embeddings = OllamaEmbeddings(model=cfg["model"], base_url=OLLAMA_BASE_URL)
        query_vector = embeddings.embed_query(question)
        if len(query_vector) != EMBEDDING_DIMENSION:
            raise ValueError(f"Query vector dimension mismatch after rebuild: expected {EMBEDDING_DIMENSION}, got {len(query_vector)}")

    # Reject zero-vector query
    if _is_zero_vector(query_vector):
        logger.warning("Rejecting search with zero-vector query.")
        return []

    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=timeout_sec)
    
    # Verify collection dimension before search
    if not _verify_collection_dimension_and_rebuild(cfg, client):
        # Rebuild happened, reconnect client
        client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=timeout_sec)

    search_kwargs = {
        "collection_name": cfg["collection"],
        "data": [query_vector],
        "anns_field": "vector",
        "search_params": {"metric_type": "COSINE", "params": {"ef": 64}}, # ef: 64 passed in search params
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
            distance = hit.get("distance", 0.0)
        else:
            entity = getattr(hit, "entity", {}) or {}
            distance = getattr(hit, "distance", 0.0)
            
        # Dense similarity thresholding using RELEVANCE_SCORE_THRESHOLD
        if distance < RELEVANCE_SCORE_THRESHOLD:
            continue
            
        text = str(entity.get("text") or "")
        if not text:
            continue
        metadata = {key: value for key, value in entity.items() if key != "text"}
        # Store score in metadata for RRF/hybrid combiner downstream
        metadata["score"] = distance
        docs.append(Document(page_content=text, metadata=metadata))
        
    return _filter_docs_by_sources(docs, target_sources or set())


def _tokenize(text: str) -> list[str]:
    """
    Tokenizer that preserves technical terms such as 'C++', 'TCP/IP', 'Node.js', and 'Llama-3.3'.
    Removes destructive punctuation stripping.
    """
    if not text:
        return []
    text = text.lower()
    # Match:
    # 1. c++ (or other alphabetical characters followed by ++)
    # 2. c# (or other alphabetical characters followed by #)
    # 3. Alphanumeric terms with internal dots, hyphens, or slashes (e.g., node.js, tcp/ip, llama-3.3)
    # 4. Standard alphanumeric words
    pattern = r'[a-z]\+\+|[a-z]#|[a-z0-9]+(?:[\.\-\/][a-z0-9]+)+|[a-z0-9]+'
    return re.findall(pattern, text)


def _fallback_retrieve_docs(question: str, k: int, target_sources: set[str] | None = None) -> list[Document]:
    """
    Retrieve documents using the inverted index for optimized BM25 scoring.
    Designed to act as the sparse leg of the parallel hybrid search.
    Removes heuristic raw term-frequency boosts that distort rankings.
    """
    from Milvus import _fallback_corpus_stats, _doc_source, _document_score, _is_syllabus_query
    
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
        _, heuristic_boost, page_bias = _document_score(question, doc)
        
        score = lexical_score
        # Only add heuristic_boost for syllabus queries.
        # Removing the heuristic keyword_score term frequency boost entirely as it distorts ranking.
        if _is_syllabus_query(question):
            score += heuristic_boost
            
        if score > 0:
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
    return primary_docs[:max(k, 4)]


def _retrieve_docs(question: str) -> list:
    """
    Main retrieval function orchestrating Concurrent Dense + BM25 search, 
    RRF Fusion, Deduplication, Cross-Encoder Reranking, and Neighbor Expansion.
    """
    from Milvus import _preprocess_query, _compute_dynamic_top_k, _dense_search_pipeline, _search_bm25_fallback, _rrf_fuse, _cross_encoder_rerank
    
    logger.info("REQUEST_RECEIVED | request_id=- | query='%s'", question)
    question_processed = _preprocess_query(question)
    k = _compute_dynamic_top_k(question_processed)
    target_sources = _extract_target_sources(question_processed)
    
    if target_sources:
        k = max(k, 6)
        
    # search_k is now max(40, k * 4) to expand the candidate pool for reranker
    search_k = max(40, k * 4)

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
    try:
        # Fused docs has size up to search_k = max(40, k * 4), which expands the reranker pool
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info("RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d", rerank_latency_ms, len(reranked_docs))
        
        if reranked_docs:
            return reranked_docs[:max(k, 4)]
          
        return []
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        return fused_docs[:k]


def _extract_target_sources(question: str) -> set[str]:
    """
    Extract target sources from query. Supports exact matching, normalized partial matches,
    and a mapped list of logical topic queries (e.g. 'AlphaGo', 'Transformer', 'TCP/IP').
    If source mapping fails to find any available matching source in the corpus, returns an empty set
    to search all docs instead of filtering to zero matches.
    """
    from Milvus import _available_sources
    
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
    if not normalized:
        return set()

    available_sources = sorted(_available_sources())
    if not available_sources:
        return set()

    by_lower = {source.lower(): source for source in available_sources}
    targets: set[str] = set()

    # 1. Attempt exact/normalized name match against current file catalog
    for source_lower, source in by_lower.items():
        if source_lower in normalized:
            targets.add(source)
            continue
            
        name_without_ext = os.path.splitext(source_lower)[0]
        if name_without_ext in normalized:
            targets.add(source)
            continue
            
        normalized_name = name_without_ext.replace("_", " ").replace("-", " ")
        if normalized_name in normalized:
            targets.add(source)
            continue

    # 2. Topic/logical query keyword mapping
    topic_map = {
        "alphago": "alphago_paper.pdf",
        "transformer": "attention_is_all_you_need.pdf",
        "attention is all you need": "attention_is_all_you_need.pdf",
        "dropout": "dropout_paper.pdf",
        "quicksort": ["course_materials.pdf", "algorithms_notes.pdf"],
        "quick sort": ["course_materials.pdf", "algorithms_notes.pdf"],
        "syllabus": "syllabus.pdf",
        "late assignment": "syllabus.pdf",
        "grading policy": "syllabus.pdf",
        "office hours": "syllabus.pdf",
        "calculator": "syllabus.pdf",
        "final exam": "syllabus.pdf",
        "recurrent neural network": "deep_learning_book.pdf",
        "rnn": "deep_learning_book.pdf",
        "deep learning": "deep_learning_book.pdf",
        "tcp/ip": "tcp_ip_notes.pdf",
        "tcp": "tcp_ip_notes.pdf",
    }

    for topic, mapped_sources in topic_map.items():
        if topic in normalized:
            if isinstance(mapped_sources, list):
                for ms in mapped_sources:
                    source = by_lower.get(ms.lower())
                    if source:
                        targets.add(source)
                    else:
                        # Even if not available currently, add it to targets so that it can match if present
                        targets.add(ms)
            else:
                source = by_lower.get(mapped_sources.lower())
                if source:
                    targets.add(source)
                else:
                    targets.add(mapped_sources)

    # 3. Ordinal and pattern matched sources (e.g. RAG sample 1)
    ordinal_to_number = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5
    }
    number_candidates: set[int] = set()

    for match in re.findall(r"\brag\s*sample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bsample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bpdf\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:pdf|document|sample)\b", normalized):
        number_candidates.add(int(match))

    for word, number in ordinal_to_number.items():
        if re.search(rf"\b{word}\s+(?:pdf|document|sample)\b", normalized):
            number_candidates.add(number)

    for number in number_candidates:
        candidate = f"RAG sample {number}.pdf".lower()
        source = by_lower.get(candidate)
        if source:
            targets.add(source)
        else:
            targets.add(f"RAG sample {number}.pdf")

    # Filter targets to only include ones that are in available_sources
    # If no mapped targets are in available_sources, fallback to searching all docs (by returning set())
    available_targets = {t for t in targets if t.lower() in by_lower}
    if targets and not available_targets:
        logger.info("Source mapping failed to find available sources in the indexed database for targets: %s. Falling back to search all docs.", targets)
        return set()

    return available_targets


# --- SUGGESTED MODIFICATIONS FOR SETUP_MILVUS.PY ---

# Inside setup_milvus.py, the following block:
#     print("     ollama pull mxbai-embed-large")
# Should be updated to:
#     print("     ollama pull nomic-embed-text")
# In order to align the setup messages with the standardised embedding model.
