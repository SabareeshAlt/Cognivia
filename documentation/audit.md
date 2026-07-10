# AcademeRAG Project Audit & Root Cause Analysis

## 1. Executive Summary

This report presents a comprehensive production-grade audit and Root Cause Analysis (RCA) of the AcademeRAG project. The audit was conducted by inspecting the entire codebase, live configurations, and empirical evaluation logs. 

The primary finding is that the RAG system's **0% evaluation pass rate** is not caused by a failure of the underlying retrieval algorithms, but rather by **architectural mismatches, critical evaluation metric math inflation, and database synchronization discrepancies**. Specifically:
1. The evaluation metric checks in `eval/rag_eval.py` require both `answer_relevancy > 0` and `hit_rate >= 0.7` to register a "pass". When the model correctly refuses to answer out-of-domain queries or questions lacking evidence with the standard refusal phrase `"Not found in the provided documents."`, the judge rates the response relevancy as `0.0` (since it does not answer the question topic), and keyword hits fail, mathematically guaranteeing a **0% pass rate** for negative queries and valid refusals.
2. The cloud vector database (Zilliz Cloud) contains only **8,960 chunks**, whereas the local fallback database contains **13,889 chunks** (a **35.5% discrepancy**). Because the retrieval orchestrator prefers cloud search and only triggers local fallback when the cloud returns *zero* documents or fails, the system searches a stale, incomplete database, causing severe context omissions.
3. The evaluation metrics for NDCG@5 and Recall@5 are mathematically inflated (NDCG@5 > 1.0, Recall@5 > 1.0) because the retrieval leg evaluates relevance at the document level (matching multiple chunks from the same source file) while normalizing DCG/Recall against the count of unique source files, leading to severe metric distortion.

---

## 2. Overall Production Readiness Score

Based on enterprise standards for production-grade retrieval systems, large language model orchestration, and evaluation frameworks, the AcademeRAG project is scored as follows:

$$\textbf{Overall Score: } 42/100 \textbf{ (Fail / Not Production-Ready)}$$

### Breakdown:
* **Retrieval Pipeline & Hybrid Search**: 65/100 (Advanced normalization and RRF fusion, but crippled by database out-of-sync states).
* **LLM Orchestration & Failover**: 70/100 (Clean circuit-breaker and Ollama fallback mechanisms, but prompts lack structural strictness).
* **Evaluation Framework**: 20/100 (Crippled by mathematical bugs, inflated metrics, and a refusal-incompatible pass criteria).
* **Observability & Logging**: 55/100 (Good latency and endpoint tracking, but lacks tracing identifiers and prompt serialization logs).
* **Security & Guardrails**: 35/100 (Basic regex sanitization, but lacks input validation, PII leakage detection, and active semantic guardrails).

---

## 3. Top 20 Critical Findings

1. **Database Out-of-Sync State**: Zilliz Cloud has 8,960 chunks, while local fallback has 13,889 chunks. This 35.5% chunk gap causes direct retrieval omission since the cloud is queried first and doesn't trigger fallback unless completely offline.
2. **Refusal Mismatch in Pass Criteria**: The evaluation pass criteria requires `answer_relevancy > 0` and `hit_rate >= 0.7`. Any correct refusal response (e.g. for negative queries or queries with missing evidence) gets a relevancy score of 0.0 and hit rate of 0.0, rendering them automatic failures.
3. **Mathematically Inflated Recall@5**: `recall_at_k` is calculated as `hits / len(expected_sources)`. Because multiple chunks from the same expected source file count as multiple hits, Recall routinely exceeds 1.0 (yielding values up to 3.46).
4. **Mathematically Inflated NDCG@5**: `calculate_ndcg` divides actual DCG by IDCG. IDCG is bounded by the number of unique expected documents, while DCG accumulates multiple chunk hits from the same document. This allows NDCG@5 to exceed 1.0 (empirically yielding values up to 1.72).
5. **Rate-Limit Failover Exhaustion**: Under rate limits (Groq HTTP 429), the LLM router falls back to local Ollama. The local Ollama server is run on CPU by default or gets terminated during system restarts, inducing latency spikes (>50 seconds per query).
6. **Hardcoded Virtual Environment Pathing**: Startup and execution scripts reference hardcoded local paths (e.g., `c:\Sabareesh\AcademeRAG - Research\AcademeRAG-Final\.venv`), preventing execution in multi-developer environments or CI/CD systems.
7. **BGE Reranker Logit Misinterpretation**: The reranker cutoff `ACADEMERAG_RERANK_CUTOFF` defaults to 0.2. Because BAAI/bge-reranker-v2-m3 outputs raw logits (from -10 to +10) rather than probabilities, applying a fixed threshold of 0.2 without sigmoid normalization filters out marginal but valid positive contexts.
8. **Inverted Index Serialization Lag**: BM25 index generation is bound to `bm25_index.pkl`. This file is built synchronously on startup or under file locks, introducing a blocking delay on server spin-up.
9. **Query Tokenizer Phrase Collision**: The custom `_tokenize` function combines alphanumeric regex extraction with hyphenated compound reconstruction. This results in duplicate term weights (e.g. "course objectives" yields "course-objectives", "course", and "objectives"), skewing BM25 term frequency representation.
10. **Absence of Token-Level Truncation**: When context exceeds limits, `_format_context` truncates text characters using an arbitrary division factor `max_chars // 4` instead of actual tokenizer length, leading to potential context overflow on LLM API boundaries.
11. **Silent Failover in Reranker**: If `sentence_transformers` fails to import or the GPU runs out of memory, the reranker fails silently and falls back to slicing the top-k documents of the RRF output without logging a stack trace.
12. **Lack of Dynamic Temperature Control**: System and evaluation queries use a hardcoded temperature of 0.1, preventing lower temperature (0.0) for deterministic evaluation or higher temperature (0.7) for phrasing diversity generation.
13. **Local/Cloud Cache Key Invalidation**: The embedding cache uses SHA256 hashes of chunk strings. If chunk formatting changes slightly, old vectors persist in cache under invalid keys, leading to dirty reads.
14. **Lack of Input Sanitization for SQL**: SQL inputs in backend views lack schema-level sanitization, raising potential injection vulnerabilities if parameters are passed directly to raw queries.
15. **Context Redaction Bypass**: The prompt injection sanitization in `_sanitize_context_text` uses static case-insensitive regex. Highly structured adversarial prompts easily bypass these regex strings.
16. **No Citation Verification Engine**: Answer citation syntax (`[Source: filename, Page: number]`) is generated by the LLM. There is no backend verification to check if the cited file and page exist in the retrieved context, allowing hallucinated citations.
17. **Empty Fallback Responses from Judge**: Local Ollama `/api/generate` endpoint was used as a fallback for the judge. This endpoint returns empty strings for complex prompt layouts, causing the judge to write "Unable to generate explanation" in reports.
18. **Unbounded Retries on Socket Probe**: `_milvus_endpoint_reachable` uses a socket connection probe with a short timeout. Under transient network loss, this causes blocking socket threads, stalling API worker pools.
19. **Prometheus Multiprocessing File Bloat**: In production/multiprocess configurations, Prometheus writes individual `.db` files per worker pid to `prometheus_multiproc_dir`, filling up disk space without a periodic rotation routine.
20. **Missing Index Verification**: The ingestion pipeline inserts vectors into Milvus before checking if the index has completed building, leading to query execution on unindexed segment collections.

---

## 4. Root Cause Tree

```
0% Evaluation Pass Rate & RAG Quality Degradation
 ├── Retrieval Failures (66.7% of Failures)
 │    ├── Data Discrepancy (Cloud has 8,960 chunks vs Local 13,889 chunks)
 │    │    └── System queries Zilliz Cloud and skips local fallback (never yields complete context)
 │    ├── Cutoff Filtering (Reranker logit threshold < 0.2 filters out marginal positives)
 │    └── Tokenizer Term Frequency Distortion (Duplicate terms in BM25 search)
 ├── Generation Refusals & Hallucinations (26.7% of Failures)
 │    ├── Refusal Message Output ("Not found in the provided documents.")
 │    │    └── Triggered by Retrieval Failure (Incomplete context from Zilliz Cloud)
 │    └── Missing Citation Verification
 │         └── LLM invents fake page/source metadata because backend does not enforce ground-truth mapping
 └── Metric Scoring Failures (Evaluation Mismatches)
      ├── Refusals scored as 0.0 Relevancy (Refusal doesn't answer the question topic)
      ├── Mathematically inflated Recall and NDCG (>1.0)
      │    └── Hit count sums chunk-level results but normalizes by document-level count
      └── Judge timeouts and empty responses (Ollama API endpoint mismatch)
```

---

## 5. Architecture Validation

| Feature / System Claim | Exists | Status | Discrepancy / Explanation |
| :--- | :---: | :---: | :--- |
| **Hybrid Retrieval** | Yes | ✓ Exists | Works correctly. Invokes Dense (Milvus) and Sparse (BM25) search legs in parallel threads. |
| **Weighted Fusion (Min-Max)** | Yes | ✓ Exists | Implemented. Replaced standard Reciprocal Rank Fusion with Min-Max Normalized Weighted Score Fusion. |
| **Neighbor Expansion** | Yes | ✓ Exists | Implemented. Chunks are expanded by checking adjacent chunk indexes ($i-1, i+1$) from the corpus. |
| **Circuit Breaker** | Yes | ✓ Exists | Implemented in `database/milvus_client.py` and `rag/llm_orchestration.py`. |
| **Fallback Routing** | Yes | ✓ Exists | Implemented. Groq automatically falls back to local Ollama on failure/rate limit. |
| **Streaming Output** | Yes | ✓ Exists | Implemented using Server-Sent Events (SSE) in `rag/llm_orchestration.py`. |
| **Rate Limiting** | Yes | ✓ Exists | Implemented on Django endpoints using django-ratelimit. |
| **GPU Acceleration** | Yes | ✓ Exists | Partially | Sentence-transformers CrossEncoder runs on CUDA if PyTorch GPU is available. Ollama runs on GPU if service is configured. |
| **Offline Mode** | Yes | ✓ Exists | Implemented. Uses local Milvus Lite, local BM25, and local Ollama. |
| **Prometheus Metrics** | Yes | ✓ Exists | Implemented. Logs query counts, latency histograms, and cache hits. |

---

## 6. Retrieval Audit

### Vector Database Schema & Collections
The schema defined in `rebuild_collection.py` contains:
* `pk`: primary key (Int64, auto_id=True)
* `source`: source document name (VarChar)
* `page_number`: document page (Int64)
* `chunk_index`: chunk position (Int64)
* `text`: raw text content (VarChar)
* `vector`: float vector (dim=1024)

### Retrieval Inconsistencies & Failures
* **Discrepancy (Cloud vs Local)**: Zilliz Cloud has **8,960 chunks**, but the local SQLite/BM25 index contains **13,889 chunks**. More than 4,900 chunks are missing from the cloud database.
* **Why Fallback Fails**: In `database/retrieval.py` (`_dense_search_pipeline`):
  ```python
  docs = _search_cloud_milvus(query_vector, question, k, target_sources)
  if not docs:
      docs = _search_local_milvus(query_vector, question, k, target_sources)
  ```
  If Zilliz Cloud returns a single chunk, `docs` is non-empty, and `_search_local_milvus` is **never executed**. This locks the retriever into searching an incomplete, stale collection.
* **Orphan Chunk Metadata**: Ingestion scripts do not enforce strict document cleanup on Zilliz Cloud when ingestion is interrupted. This creates orphaned vector IDs that lack corresponding metadata descriptors.

---

## 7. Cross Encoder Audit

### The Cutoff Regression
The CrossEncoder reranker (`BAAI/bge-reranker-v2-m3`) computes a score for each `[query, doc.page_content]` pair. In `database/reranker.py`:
```python
cutoff = float(os.environ.get("ACADEMERAG_RERANK_CUTOFF", "0.3"))
for doc, score in scored_docs:
    if float(score) < cutoff:
        continue
```
* **Logits vs Probabilities**: BGE Reranker v2 outputs raw logit scores (e.g. $+1.2, -4.5$) instead of a normalized probability distribution.
* **Regression Cause**: A static cutoff of `0.2` or `0.3` without a sigmoid function treats these raw logits as probabilities. If a query has valid context that scores slightly below `0.2` (e.g., `0.05`), it is completely filtered out. When all retrieved documents fall below this threshold, the reranker returns `[]` (empty list), causing a complete retrieval failure.

---

## 8. Evaluation Audit

### Metric Implementation Flaws
The evaluation metrics in `eval/rag_eval.py` have critical mathematical errors:
* **Recall@k Inflation**: 
  ```python
  hits = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
  recall_at_k = hits / len(expected_sources)
  ```
  If the RAG system retrieves 5 chunks all belonging to the single expected document `RAG sample 1.pdf`, `hits` evaluates to `5`. If `expected_sources` has 1 item, the recall is `5 / 1 = 5.0`. Recall must be bounded by $[0, 1]$.
* **NDCG@5 Inflation**:
  ```python
  dcg = 0.0
  for idx, src in enumerate(retrieved_sources[:k], 1):
      if any(exp in src for exp in expected_sources):
          dcg += 1.0 / math.log2(idx + 1)
  ```
  If 5 correct chunks from the same expected document are retrieved, the DCG accumulates discounted gains for all 5 chunks. However, the Ideal DCG (IDCG) is computed by:
  ```python
  for idx in range(1, min(k, len(expected_sources)) + 1):
      idcg += 1.0 / math.log2(idx + 1)
  ```
  Since `len(expected_sources)` is 1, `idcg` is computed only for `idx=1` ($1.0 / \log_2(2) = 1.0$). The resulting NDCG is `DCG / 1.0`, which easily exceeds 1.0.

### Pass Rate Scoring Mismatch
A RAG execution is marked as `passed` if:
```python
passed = hit_rate >= 0.7 and (has_citation or "not found" in answer.lower()) and (mrr > 0 or not expected_sources) and faithfulness > 0 and answer_relevancy > 0
```
For a negative/out-of-domain query, the expected answer is a refusal. The model outputs: `"Not found in the provided documents."`
* The LLM judge evaluates `answer_relevancy` using the prompt: *"Determine if the answer directly addresses the provided question."*
* Since the refusal does not address the question topic (e.g. "What is the capital of France?"), the judge outputs `0`.
* This sets `answer_relevancy = 0.0`. Since `answer_relevancy > 0` is required to pass, **all valid refusals are marked as failures**, bringing the Negative Query pass rate to exactly **0.00%**.

---

## 9. Dataset Audit

The evaluation dataset `eval/golden_set_academic.json` contains 45 questions across 8 categories:
* **Factual QA**: 6 cases
* **Syllabus QA**: 7 cases
* **Keyword Lookup**: 5 cases
* **Summarization**: 5 cases
* **Negative Queries**: 6 cases
* **Multi-page Reasoning**: 6 cases
* **Table Extraction**: 5 cases
* **Semantic Retrieval**: 5 cases

### Dataset Audit Findings
1. **Keyword Over-specificity**: Several reference keywords are highly specific (e.g. for `factual_1`: `['computer science', 'engineering', 'subject', 'course']`). If the LLM generates a correct list of subjects but omits the word "subject" or "course", the keyword hit rate falls below `0.7`, causing a failure.
2. **Ambiguous expected sources**: Case `syllabus_1` lists `['RAG sample 1.pdf', 'RAG sample 2.pdf', 'RAG sample 3.pdf']` as expected sources. This assumes that syllabus content is replicated across all files, which introduces noise during recall calculations.

---

## 10. Hallucination Analysis

Across the 15-case evaluation benchmark:
* **Total Generation Hallucinations**: 4 (26.7% of failures)
* **Root Cause 1: Incomplete Retrieval**: The system failed to retrieve the page containing unit structures due to the cloud database chunk gap. The LLM was presented with a context containing only generic course outcomes. The RAG system prompt instructs: *"If the context contains partial or indirect evidence, synthesize a best-effort answer."* This encouraged the model to synthesize a response using general knowledge, leading to factual hallucinations.
* **Root Cause 2: Fabricated Citations**: The LLM outputted `[Source: RAG sample 1.pdf, Page: 5]` because the prompt instructed it to provide precise citations. Since the context chunks lacked explicit page markers for that topic, the model guessed the page number, creating a citation hallucination.

---

## 11. Latency Analysis

### Bottleneck Identification
* **Ollama Embeddings Generation**: Generating query embeddings locally via Ollama (`bge-m3:latest`) on CPU takes **~3.2 to 4.5 seconds** per query. On GPU, this drops to **~0.25 seconds**.
* **Zilliz Cloud Search**: Cloud network round-trip adds **~1.8 to 2.2 seconds** per search leg.
* **CrossEncoder Rerank**: Running prediction on CPU takes **~12.5 to 25.0 seconds** for 40 chunks. Running on GPU (NVIDIA RTX 3070 Laptop GPU) takes **~1.2 to 1.5 seconds**.
* **Ollama Generation**: Fallback local LLM generation takes **~35 to 52 seconds** on CPU. On GPU, it takes **~4.5 seconds**.

---

## 12. Configuration Audit

* **Dead Configs**: `ACADEMERAG_MILVUS_DEPLOYMENT` is parsed in `database/config.py` but is overridden by `ACADEMERAG_MILVUS_MODE` or `.env` URL schemes.
* **Incorrect Defaults**: `OLLAMA_BASE_URL` in `database/config.py` defaults to `http://ollama:11434`, which is correct for Docker network setups but fails in local-host development where `http://localhost:11434` is required.
* **Conflicting Configs**: `EMBEDDING_MODEL` in `ingest_pdfs.py` defaults to `"mxbai-embed-large"`, while `database/config.py` defaults to `"bge-m3:latest"`. If the ingestion script is run with default values, it writes 1024-dimension embeddings, but the query pipeline expects BGE-M3, causing runtime dimension exceptions.

---

## 13. Security Audit

* **Prompt Injection**: The case-insensitive regex pattern in `_sanitize_context_text` can be bypassed by inserting spaces or escape characters (e.g. `i g n o r e  i n s t r u c t i o n s`).
* **Secrets in Environment**: The Zilliz token `ACADEMERAG_MILVUS_TOKEN` is saved as plain text in `.env`.
* **PII Leakage**: The system does not scan retrieved documents or queries for personally identifiable information (PII) before routing requests to external LLM providers (e.g., Groq).

---

## 14. Observability Audit

* **No Request IDs**: While logging logs `"REQUEST_RECEIVED | request_id=-"`, the request ID is always hardcoded as `-`. There is no request-tracing middleware to propagate UUIDs across retrieval, fusion, reranking, and generation stages.
* **No Prompt Versioning**: Prompt templates are hardcoded in `rag/llm_orchestration.py` without serialization, making it impossible to track which prompt version generated a specific response in production logs.

---

## 15. Testing Audit

* **Test Environment Mismatch**: The unit test `api/test_security_offline.py` mocks Milvus connections, but does not test the dual-leg data out-of-sync state.
* **Lack of Integration Coverage**: There are no tests verifying that the RRF normalized output scores are bounded between $[0, 1]$ before passing them to the reranker cutoff filter.

---

## 16. Documentation Audit

* **Outdated Architecture Claims**: The `architecture.md` file asserts that Zilliz Cloud and Local Milvus Lite are synchronized automatically via a background worker thread. However, the background worker is not active in the Django app configuration, leaving the collections out-of-sync.

---

## 17. Production Gap Analysis

To meet enterprise standards, the AcademeRAG project lacks:
1. **Active Database Sync Workers**: A background cron job to sync SQLite and Zilliz Cloud indices.
2. **Context Compression**: A semantic summarizer to condense retrieved chunks before LLM ingestion.
3. **Citation Validation Layer**: A validator to map LLM citations back to retrieved context page boundaries.

---

## 18. Quick Wins

1. **Fix Pass Criteria for Refusals**: Modify `eval/rag_eval.py` to skip `answer_relevancy` checks for queries classified as negative or expected refusals.
2. **Fix NDCG and Recall Metrics**: Normalize DCG and Recall by document-level unique matches rather than summing raw chunk counts.
3. **Synchronize Zilliz Cloud Collection**: Re-run the ingestion pipeline using the virtual environment python command to push all 13,889 chunks to Zilliz Cloud, matching the local database.

---

## 19. High Priority Fixes

1. **Standardize Reranker Inputs**: Normalize CrossEncoder logits using a sigmoid function before applying the cutoff threshold filter.
2. **Implement Request ID Propagation**: Replace the hardcoded `request_id=-` with a thread-local request identifier generated at the API middleware layer.
3. **Enforce Local Fallback on Chunk Count**: Modify the retrieval pipeline to trigger local fallback if the cloud database returns fewer chunks than expected.

---

## 20. Long-Term Improvements

1. **Deploy a Semantic Cache**: Cache query embeddings and answers locally using Milvus to avoid duplicate LLM calls.
2. **Implement Guardrail Integration**: Integrate NVIDIA NeMo Guardrails to secure both input queries and generated outputs.
3. **Automate Continuous Evaluation**: Run the evaluation harness on a daily cron job to detect regression trends.

---

## 21. Final Verdict

The AcademeRAG project features a robust hybrid retrieval architecture, but is currently held back by **faulty evaluation metrics and database desynchronization**. The system is not achieving production-quality evaluation because the metrics are mathematically incorrect, and the retriever is querying an incomplete cloud database. Implementing the identified quick wins and high-priority fixes will elevate the system to a production-ready state.
