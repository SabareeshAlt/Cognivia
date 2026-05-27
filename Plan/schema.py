import time
import logging
from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient

logger = logging.getLogger(__name__)

def ensure_collection_schema(cfg: dict, embeddings, recreate: bool = False) -> bool:
    """Ensure collection exists with explicit schema before ingestion."""
    # Assume _connect_milvus_client, _wait_for_collection_absence, 
    # _wait_for_collection_presence, _get_embedding_dimension are available.
    client = _connect_milvus_client(cfg)
    exists = client.has_collection(cfg["collection"])

    if exists and recreate:
        logger.info("Dropping existing Milvus collection: %s", cfg["collection"])
        client.drop_collection(cfg["collection"])
        _wait_for_collection_absence(client, cfg["collection"])
        exists = False

    if exists:
        return True

    dim = _get_embedding_dimension(embeddings)
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

    # Add scalar indexes for these fields using client.create_index() to optimize metadata filtering.
    scalar_index_params = MilvusClient.prepare_index_params()
    scalar_index_params.add_index(field_name="source", index_name="source_idx")
    scalar_index_params.add_index(field_name="page_number", index_name="page_number_idx")
    scalar_index_params.add_index(field_name="chunk_index", index_name="chunk_index_idx")
    
    client.create_index(collection_name=cfg["collection"], index_params=scalar_index_params)
    
    return True

def _ingest_documents_with_client(cfg: dict, embeddings, docs) -> None:
    # Assume _connect_milvus_client_with_timeout, MILVUS_INIT_TIMEOUT_SECONDS,
    # INGEST_BATCH_SIZE, INGEST_MAX_SECONDS are available.
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=MILVUS_INIT_TIMEOUT_SECONDS)
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
