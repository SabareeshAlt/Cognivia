# RAG Architecture

## Flow

1. PDFs are loaded from `documents/`.
2. Text is chunked with configured `CHUNK_SIZE` and `CHUNK_OVERLAP`.
3. Chunks are embedded via Ollama embeddings model.
4. Embeddings are written to Milvus collection.
5. Ask endpoints retrieve context from Milvus and generate answer via Ollama LLM.
6. If no context is retrieved, deterministic fallback response is returned.

## Hardening Controls

- Idempotent sync decision using content hashes + chunk profile.
- Bounded ingestion batch size and ingest timeout.
- Dynamic top-k retrieval bounds (`ACADEMERAG_TOP_K_MIN/MAX`).
- Relevance score threshold filter (`ACADEMERAG_SCORE_THRESHOLD`).
- Admin-only retrieval diagnostics endpoint.

## Operational Signals

- Health probes: liveness + readiness
- Metrics endpoint: request counters and latency buckets
- Request-level trace IDs for all API responses

