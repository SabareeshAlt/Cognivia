# Backend Retrieval Audit Report

Date: 2026-02-17  
Scope: Indexing lifecycle, Milvus retrieval path, API robustness, operational safety

## Executive Summary

- Indexing is **not performed on every app run** in the active backend path.
- Current production retrieval path is `api/views.py` -> `Milvus.py`.
- Retrieval is functional, but robustness is limited by cold-start latency, missing ingestion lifecycle controls, and duplicate/legacy retrieval modules.

## Indexing Behavior (Answer to your question)

- Active runtime path (`api/views.py`) imports `Milvus.get_retriever` (not `vector.py`) at `api/views.py:34`.
- `Milvus.get_retriever()` calls `initialize_vector_store(force_reindex=False)` at `Milvus.py:285`.
- With `force_reindex=False`, backend only connects to existing collection and runs a probe query (`similarity_search`) at `Milvus.py:264`.
- Reindexing is currently manual via `setup_milvus.py` which explicitly calls `initialize_vector_store(force_reindex=True)` at `setup_milvus.py:97`.

Conclusion: indexing is effectively a **one-time/manual operation**, not per-run.

## Findings (Severity-Ordered)

### High

1. Cold-start request path performs heavyweight dependency initialization  
   - Retrieval/embedding clients are initialized on first request and also on health checks via `get_retriever()` (`api/views.py:129-133`, `Milvus.py:285`).
   - Impact: first user request can be slow/fail under transient Milvus/Ollama issues; health endpoint can trigger expensive dependencies.

2. No ingestion state/versioning or idempotency checks for corpus refresh  
   - Reindexing is all-or-nothing via `force_reindex=True` (`setup_milvus.py:97`, `Milvus.py:231-249`) without document hash/version tracking.
   - Impact: hard to do safe incremental updates; risk of stale/duplicate semantic content across ingestion cycles.

3. Legacy duplicate retrieval stack causes architecture drift and operational risk  
   - `Milvus.py` (active) and `vector.py`/`api/views_integrated.py` (legacy/alternate) implement conflicting behavior and APIs.
   - Example mismatch: `views_integrated.py` calls `get_retriever(k=...)` (`api/views_integrated.py:85`, `:157`) but `vector.get_retriever()` takes no args (`vector.py:127`).
   - Impact: high chance of breakage if routes/imports are switched during future refactors.

### Medium

4. Health endpoint conflates readiness and liveness  
   - `api/health/` triggers external dependencies (`api/views.py:128-135`) and can report degraded during transient vector outages.
   - Impact: orchestrators/load balancers may treat dependency flaps as app-unhealthy.

5. Empty-collection behavior is not explicitly guarded at answer stage  
   - System logs may show vector store operational with `0` results; answer path still builds chain from retriever (`Milvus.py:299+`).
   - Impact: potential low-quality answers if retrieval returns insufficient context.

6. Retrieval parameterization is partly hardcoded  
   - `k=3` is fixed in active retriever (`Milvus.py:289`) and chunking values are hardcoded (`Milvus.py:158-159`), ignoring env knobs like `ACADEMERAG_TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`.
   - Impact: limited tunability across environments and workloads.

### Low

7. Minor operational noise/quality issues  
   - Non-ASCII log glyph artifact in force-reindex log (`Milvus.py:232`).
   - Warning suppression is broad (`Milvus.py:11-12`), potentially hiding useful deprecation signals.

## Robustness Scorecard (Current)

- Retrieval availability: Medium  
- Ingestion lifecycle maturity: Low  
- Configuration hygiene: Medium  
- Operability/observability: Medium  
- Change safety (maintainability): Low-Medium

## Recommended Backend Upgrades (Priority Plan)

1. Split health endpoints into:
   - `/api/health/live` (process-only, fast)
   - `/api/health/ready` (dependency checks with short timeout budget)

2. Add ingestion state model (DB table or Milvus metadata collection):
   - `document_id`, `content_hash`, `indexed_at`, `embedding_model`, `chunk_profile`
   - Only re-embed changed/new docs.

3. Remove or archive legacy retrieval path:
   - Keep one canonical retrieval implementation (`Milvus.py` or a new service module).
   - Delete/retire `vector.py` + `views_integrated.py` or gate them clearly as deprecated.

4. Externalize retrieval tuning to env:
   - `ACADEMERAG_TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, timeout/retry budgets.

5. Add graceful answer fallback policy:
   - If `docs == 0`, return deterministic “insufficient indexed data” response unless explicitly allowing model-only answers.

6. Add retrieval-focused tests:
   - Mocked Milvus unavailable/timeouts
   - Empty collection behavior
   - Incremental reindex idempotency
   - Health live vs ready semantics

## Direct Answer

- Your current system does **not** reindex every run.
- It performs **connect + probe** on first retriever access per process, and full indexing only when `force_reindex=True` (manual setup path).
