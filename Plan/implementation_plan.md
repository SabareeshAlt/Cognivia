# AcademeRAG Production-Readiness Audit

**Audit Date**: 2026-05-26
**Auditor**: Antigravity AI — Principal Architect + Retrieval + LLM + Vector DB + Security + Reliability Review
**Target**: Production-grade, on-premise RAG chatbot for institutional use
**Deployment**: Local/on-premise only | Self-hosted Ollama | 10-50 PDFs at scale

---

## Audit Context

| Parameter | Value |
|---|---|
| Deployment | Local/on-premise only |
| LLM Strategy | Self-hosted Ollama (no cloud dependency) |
| Corpus Scale | 10-50 PDFs (moderate growth) |
| User Scale | Not yet determined |
| Intent | Production-grade product for real institutional use |

## Severity Definitions

| Level | Meaning |
|---|---|
| **P0 — Critical** | System broken, data loss, security breach, or blocks production deployment |
| **P1 — High** | Significant reliability/quality/security risk; must fix before production |
| **P2 — Medium** | Degrades quality, maintainability, or developer experience; fix before scaling |
| **P3 — Low** | Improvement opportunity; address during regular development |

---

## 1. RAG Architecture Review

### 1.1 Architecture Topology

```
User → React Frontend (Vite) → Django API (/api/ask/) → Milvus.py RAG Engine
                                                              │
                                          ┌───────────────────┼───────────────────┐
                                          ▼                   ▼                   ▼
                                  Milvus Cloud         Direct MilvusClient    BM25 Local
                                  (LangChain)          (pymilvus)             (Custom)
                                          │                   │                   │
                                          └───────────────────┼───────────────────┘
                                                              ▼
                                                    Context Assembly
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                        Syllabus        Groq Cloud       Local Ollama
                                        Shortcut        (ChatOpenAI)     (ChatOllama)
                                        (No LLM)
```

### 1.2 Findings

#### F1.1 — Monolithic RAG Engine (P2)
**Evidence**: [Milvus.py](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py) is **1903 lines** containing retrieval, chunking, ingestion, BM25, LLM failover, circuit breakers, syllabus heuristics, prompt templates, and diagnostics in a single file.

**Impact**: Untestable in isolation, impossible to swap components, high cognitive load for maintenance.

**Recommendation**: Decompose into focused modules:
- `rag/chunking.py` — text splitting, PDF loading
- `rag/retrieval.py` — vector search, BM25, scoring
- `rag/llm.py` — provider management, failover
- `rag/prompts.py` — prompt templates
- `rag/ingestion.py` — batch indexing, tracking
- `rag/config.py` — all env var loading
- `rag/heuristics.py` — syllabus/subject detection

---

#### F1.2 — Groq Cloud Dead Weight (P1)
**Evidence**: [Milvus.py:139-144](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L139-L144) configures Groq API key, base URL, model, timeouts, and circuit breaker. [Milvus.py:1723-1810](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1723-L1810) implements Groq health checking, URL validation, and reachability probes. [Milvus.py:1816-1867](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1816-L1867) implements provider failover between Groq and Ollama.

**Impact**: User confirmed self-hosted Ollama only. ~150 lines of Groq code adds complexity, import dependencies (`langchain-openai`), network probes on startup, and a circuit breaker that serves no purpose. The `langchain-openai` dependency previously caused a production crash.

**Recommendation**: Remove all Groq-related code, config, and the `langchain-openai` dependency. Simplify to a single Ollama provider path. If multi-provider support is needed later, design a proper plugin interface.

---

#### F1.3 — sys.path Manipulation for Imports (P2)
**Evidence**: [api/views.py:20-21](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/views.py#L20-L21) appends `parent_dir` to `sys.path` to import `Milvus.py`.

**Impact**: Fragile import path. Can cause import conflicts if directory structure changes. Not idiomatic Django.

**Recommendation**: Convert `Milvus.py` to a proper Python package (`rag/`) and install via `pip install -e .` or add to Django's module structure.

---

#### F1.4 — Hot-Reload via File mtime Check (P2)
**Evidence**: [api/views.py:40-63](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/views.py#L40-L63) checks `Milvus.py` file modification time on every request and calls `importlib.reload()` if changed.

**Impact**: Useful for development but dangerous in production. Module-level side effects (like `_schedule_fallback_cache_refresh()` at [Milvus.py:1902](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1902)) re-execute on reload. Thread-safe globals get reset. Can cause request failures during reload.

**Recommendation**: Guard behind `DEBUG` mode. Disable in production.

---

#### F1.5 — Module-Level Side Effects (P1)
**Evidence**: [Milvus.py:1902](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1902) calls `_schedule_fallback_cache_refresh()` on import. This reads all PDFs, chunks them, and builds BM25 stats in a background thread — triggered just by importing the module.

**Impact**: Every `importlib.reload()` re-triggers PDF parsing. If import fails partway, the module is partially initialized. Unpredictable startup behavior.

**Recommendation**: Move initialization to an explicit `startup()` function called by Django's `AppConfig.ready()` or the warmup flow.

---

## 2. Retrieval Quality & Accuracy Review

### 2.1 Retrieval Pipeline

The system implements a **4-tier retrieval cascade** ([Milvus.py:1512-1596](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1512-L1596)):

1. LangChain Milvus `similarity_search_with_relevance_scores` (threshold = 0.35)
2. Plain `similarity_search` (no threshold)
3. Direct `MilvusClient.search()` (bypasses LangChain)
4. BM25 local fallback

### 2.2 Findings

#### F2.1 — Hardcoded General Curriculum Bypass (P0)
**Evidence**: [Milvus.py:1513-1533](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1513-L1533) checks if the question matches a general CSE curriculum pattern and directly returns pages 3-8 of `RAG sample 3.pdf` with `chunk_index=0`.

**Impact**: This is a **hardcoded hack** that:
- Breaks if the PDF is updated, renamed, or restructured
- Returns raw page text without any relevance scoring
- Bypasses the entire retrieval pipeline for a broad class of queries
- Cannot generalize to new departments or curricula
- Represents "if-else engineering" rather than retrieval engineering

**Recommendation**: Remove entirely. If curriculum overview queries consistently fail via standard retrieval, the root cause is a chunking or embedding problem — fix those instead of hardcoding bypasses.

---

#### F2.2 — Hardcoded Domain-Specific Scoring Boosts (P1)
**Evidence**: [Milvus.py:1058](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1058): `"digital logic design" → +4 boost`. [Milvus.py:1059-1065](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1059-L1065): penalties for "course objectives" (-4), "program outcomes" (-4), "assessment methodology" (-5).

**Impact**: These boosts and penalties are specific to the current 3-PDF corpus. They will not generalize when the corpus grows to 10-50 PDFs. New subjects will not receive appropriate scoring unless manually added. This is the antithesis of a scalable retrieval system.

**Recommendation**: Replace with a metadata-based scoring approach. Tag chunks with `section_type` (syllabus, objectives, assessment) during ingestion and apply section-type weights at query time, driven by config, not hardcoded conditions.

---

#### F2.3 — Syllabus Shortcut Bypasses LLM Entirely (P1)
**Evidence**: [Milvus.py:1283-1324](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1283-L1324) — `_extract_syllabus_text()` directly extracts raw PDF text for single-subject syllabus queries and returns it without any LLM processing. Called at [Milvus.py:1872-1874](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1872-L1874).

**Impact**: Returns raw, uncurated text to the user. No formatting, no summarization, no ability to answer follow-up questions about the syllabus. Users get a wall of text instead of a conversational answer. This undermines the purpose of the LLM layer.

**Recommendation**: Remove the direct extraction path. Instead, use the extracted text as **context** for the LLM, allowing it to format and present the syllabus properly. If verbatim accuracy is needed, the prompt can instruct the LLM to reproduce the syllabus without modification.

---

#### F2.4 — No Re-ranking Stage (P2)
**Evidence**: Retrieved documents are scored by vector similarity (Milvus) or BM25+heuristics (fallback), but there is no cross-encoder or LLM-based re-ranking step before context assembly.

**Impact**: Top-k results may include low-relevance chunks that dilute context quality. With `k=3-6`, every slot matters.

**Recommendation**: Add a lightweight re-ranking step using either:
- Cross-encoder model (e.g., `sentence-transformers/cross-encoder/ms-marco-MiniLM-L-6-v2`)
- LLM-based relevance scoring (ask Ollama to rate each chunk's relevance 0-10)

---

#### F2.5 — Relevance Threshold Silently Lowered (P2)
**Evidence**: [Milvus.py:1565](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1565) — when source filter is active, threshold drops from 0.35 to `0.35 * 0.6 = 0.21`. If no docs pass even that, all scored docs are used regardless ([Milvus.py:1567-1568](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1567-L1568)).

**Impact**: Undocumented behavior. Source-filtered queries can return very low-quality chunks. The "use all if none pass" fallback means threshold filtering is effectively disabled for source-specific queries.

**Recommendation**: Log when threshold is lowered. Set a hard floor (e.g., 0.15) below which chunks are never returned. Remove the "use all" fallback.

---

#### F2.6 — No Query Preprocessing or Expansion (P2)
**Evidence**: Questions go directly to embedding and BM25 without any preprocessing.

**Impact**: Misspellings, abbreviations (e.g., "CS" vs "Computer Science"), and ambiguous queries degrade retrieval. No synonym expansion, no acronym resolution.

**Recommendation**: Add a lightweight query preprocessing step: spell check, acronym expansion (configurable dictionary), and optionally LLM-based query rewriting.

---

## 3. Hybrid Search Feasibility Review

### 3.1 Current State

The system has a **sequential fallback** approach, not true hybrid search:
- Try Milvus vector search → if fails → try BM25

### 3.2 Findings

#### F3.1 — BM25 is Fallback-Only, Not Hybrid (P2)
**Evidence**: BM25 is only invoked when all three Milvus paths fail ([Milvus.py:1575-1578](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1575-L1578)). Vector and lexical search never run in parallel.

**Impact**: The system never benefits from the complementary strengths of vector (semantic) + lexical (exact keyword) search simultaneously. Keyword-heavy queries that semantic search handles poorly get zero BM25 contribution.

**Recommendation**: Implement **Reciprocal Rank Fusion (RRF)** to combine vector and BM25 results:
```
RRF_score(doc) = Σ 1 / (k + rank_i(doc))
```
Run both Milvus and BM25 for every query, merge results, deduplicate by chunk content hash.

---

#### F3.2 — BM25 Implementation Quality (P2)
**Evidence**: Custom BM25 at [Milvus.py:1373-1392](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1373-L1392). Tokenization at [Milvus.py:938](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L938) uses `re.findall(r"[a-z0-9]+", text.lower())`.

**Impact**: The tokenizer:
- Destroys compound terms (e.g., "object-oriented" → ["object", "oriented"])
- Has no stemming (e.g., "programming" vs "programs" are different tokens)
- Has a minimal stopword list (14 words at [Milvus.py:44-64](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L44-L64))
- No support for bigrams or phrases

**Recommendation**: Use `rank_bm25` library or implement stemming via `nltk.stem.PorterStemmer`. Expand the stopword list. Consider bigram support for multi-word subject names.

---

## 4. Chunking & Embedding Review

### 4.1 Current Configuration

| Parameter | Value | Source |
|---|---|---|
| Splitter | `RecursiveCharacterTextSplitter` | [Milvus.py:404](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L404) |
| Chunk Size | 1000 chars | Env `CHUNK_SIZE`, default at [Milvus.py:149](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L149) |
| Overlap | 200 chars | Env `CHUNK_OVERLAP`, default at [Milvus.py:150](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L150) |
| Separators | `["\n\n", "\n", " ", ""]` | [Milvus.py:407](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L407) |
| Embedding Model | Ollama-hosted (env-configured) | [Milvus.py:134](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L134) |

### 4.2 Findings

#### F4.1 — Character-Based Chunking for Academic PDFs (P1)
**Evidence**: `RecursiveCharacterTextSplitter` splits by character count at [Milvus.py:404-410](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L404-L410). Academic syllabi have rigid structure: `UNIT I - Title`, `UNIT II - Title`, etc.

**Impact**: A 1000-character chunk can split mid-unit, placing the unit title in one chunk and unit content in another. This is why syllabus queries fail without hardcoded bypasses — the semantic boundary between units is not preserved.

**Recommendation**: Implement **structure-aware chunking** for academic PDFs:
1. Detect unit boundaries via regex (`UNIT\s+[IVX]+`)
2. Treat each unit as a single chunk (even if > 1000 chars)
3. Add metadata: `unit_number`, `unit_title`, `subject_name`, `section_type`
4. Fall back to RecursiveCharacterTextSplitter only for non-structured content

This alone would eliminate the need for `_extract_syllabus_text`, the general curriculum bypass, and most of the heuristic scoring code.

---

#### F4.2 — No Metadata Enrichment During Ingestion (P1)
**Evidence**: Chunk metadata at [Milvus.py:420-435](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L420-L435) includes only: `source`, `document_path`, `document_hash`, `page_number`, `chunk_index`.

**Impact**: No `section_type` (syllabus/objectives/lab/assessment), no `subject_name`, no `department`, no `regulation_year`. All the heuristic scoring at retrieval time ([Milvus.py:1042-1094](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1042-L1094)) exists because this information isn't available as metadata.

**Recommendation**: Extract and store structured metadata during ingestion:
- `section_type`: syllabus | objectives | outcomes | assessment | lab | references
- `subject_name`: parsed from PDF structure
- `department`: parsed or configured per-document
- `regulation_year`: parsed from headers
- `unit_number`: for syllabus sections

This enables filtered retrieval by metadata instead of post-hoc heuristic scoring.

---

#### F4.3 — PDF Text Extraction Quality Unknown (P2)
**Evidence**: `pypdf.PdfReader` at [Milvus.py:413](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L413) extracts text. No validation of extraction quality.

**Impact**: Academic PDFs often have tables, multi-column layouts, headers/footers, and page numbers that `pypdf` handles poorly. Extracted text may have garbled tables, merged columns, or orphaned headers.

**Recommendation**: Add extraction quality validation:
1. Log character count per page (detect empty pages)
2. Detect and strip repeated headers/footers
3. Consider `pdfplumber` as an alternative for table-heavy PDFs
4. Add a manual review step for new documents

---

#### F4.4 — Embedding Dimension Probed Wastefully (P3)
**Evidence**: [Milvus.py:628](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L628) — embedding dimension determined by embedding the string `"dimension probe"` every time collection schema is ensured.

**Impact**: Unnecessary API call to Ollama. Dimension is a fixed property of the model.

**Recommendation**: Cache dimension after first probe. Or configure it explicitly via env var.

---

## 5. Vector Database Review

### 5.1 Current Configuration

| Parameter | Value | Source |
|---|---|---|
| Provider | Milvus Cloud (Zilliz) | [Milvus.py:113-130](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L113-L130) |
| Index Type | AUTOINDEX | [Milvus.py:659](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L659) |
| Metric | COSINE | [Milvus.py:659](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L659) |
| Schema | pk (INT64), text (VARCHAR 65535), vector (FLOAT_VECTOR), dynamic fields | [Milvus.py:631-665](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L631-L665) |

### 5.2 Findings

#### F5.1 — Cloud Milvus Contradicts On-Premise Strategy (P0)
**Evidence**: [Milvus.py:113-130](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L113-L130) normalizes Zilliz Cloud URI. User confirmed local/on-premise deployment.

**Impact**: The system depends on an external cloud service for its core retrieval capability. This directly contradicts the stated deployment strategy. If Zilliz is unreachable, retrieval degrades to BM25 only.

**Recommendation**: Switch to **Milvus Lite** (file-based, embedded mode) for on-premise deployment. `pymilvus` supports `MilvusClient("./milvus_data.db")` for zero-infrastructure local operation. Keep cloud as an optional deployment target behind a config flag.

---

#### F5.2 — No Scalar Index on Metadata Fields (P2)
**Evidence**: Schema at [Milvus.py:631-665](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L631-L665) creates only a vector index. Source filtering uses `expr` parameter with `source == "..."` but no scalar index on `source`.

**Impact**: Source-filtered queries do a full scan on the `source` field before vector search. With 10-50 PDFs (potentially thousands of chunks), this becomes increasingly slow.

**Recommendation**: Add a scalar index on `source` (and on proposed `section_type`, `subject_name` fields).

---

#### F5.3 — VARCHAR(65535) for Text Field (P3)
**Evidence**: [Milvus.py:649](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L649) — `FieldSchema("text", DataType.VARCHAR, max_length=65535)`.

**Impact**: Chunks are 1000 chars with 200 overlap. Max chunk is ~1200 chars. Allocating 65535 chars wastes memory in Milvus.

**Recommendation**: Set `max_length=4096` (comfortable margin above max chunk size).

---

## 6. LLM Response Quality Review

### 6.1 Prompt Template Analysis

**Evidence**: [Milvus.py:1659-1721](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1659-L1721) — system prompt with 7 instruction sections.

### 6.2 Findings

#### F6.1 — No Grounding Verification in Prompt (P2)
**Evidence**: The prompt instructs "answer strictly from context" but does not instruct the LLM to cite which parts of the context support each claim.

**Impact**: No way for users to verify answers against source documents. No way for the system to detect hallucination.

**Recommendation**: Add citation instruction: "For each claim, cite the source document and page number in [Source: filename, Page: N] format."

---

#### F6.2 — Context Assembly Loses Structure (P2)
**Evidence**: [Milvus.py:1876](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1876) — `"\n\n".join(doc.page_content for doc in docs)`.

**Impact**: Chunks are concatenated without any structural markers. The LLM cannot distinguish between chunks from different documents or pages. If chunks from multiple PDFs are retrieved, the LLM may conflate information.

**Recommendation**: Format context with clear boundaries:
```
[Source: RAG sample 3.pdf | Page: 5 | Section: Syllabus]
<chunk content>

[Source: RAG sample 1.pdf | Page: 12 | Section: Lab Manual]
<chunk content>
```

---

#### F6.3 — No Maximum Context Length Check (P2)
**Evidence**: All retrieved + augmented chunks are concatenated into context without checking total length. With `k=6` and neighbor expansion ([Milvus.py:1465-1509](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1465-L1509)), context can grow to 10+ chunks × 1000 chars = 10K+ chars.

**Impact**: May exceed Ollama model's effective context window. Long contexts degrade response quality even within limits (lost-in-the-middle effect).

**Recommendation**: Cap context at a configured maximum (e.g., 4000 chars). Prioritize highest-scored chunks when truncating.

---

#### F6.4 — Temperature 0.7 Too High for RAG (P2)
**Evidence**: [Milvus.py:137](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L137) — `LLM_TEMPERATURE` defaults to 0.7.

**Impact**: For a RAG system that should faithfully reproduce information from context, 0.7 introduces unnecessary randomness. Industry standard for RAG is 0.0-0.3.

**Recommendation**: Default to `0.1` for factual accuracy. Allow override via env var for conversational use cases.

---

## 7. Security Audit

### 7.1 Findings

#### F7.1 — .env File Potentially Committed to Git (P0)
**Evidence**: `.env` file exists at project root (2474 bytes). Contains `DJANGO_SECRET_KEY`, `GROQ_API_KEY`, database credentials.

**Impact**: If committed, all secrets are exposed in git history permanently. Even if removed, they persist in git log.

**Recommendation**:
1. Verify with `git log --all -- .env` whether it was ever committed
2. If committed: rotate ALL secrets immediately
3. Add `.env` to `.gitignore` (verify it's actually tracked vs just present)
4. Use `.env.example` with placeholder values for documentation

---

#### F7.2 — Rate Limiting Silently Degrades to No-Op (P0)
**Evidence**: [api/rate_limit.py:3-8](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/rate_limit.py#L3-L8) — if `django_ratelimit` is not installed, the decorator becomes a passthrough. No warning logged.

**Impact**: Brute-force attacks on login endpoint are possible without the package. The system appears to have rate limiting but actually doesn't. Silent degradation is worse than no feature at all.

**Recommendation**: Make `django-ratelimit` a hard dependency. If import fails, log a CRITICAL warning and either refuse to start or enable a simple in-memory rate limiter.

---

#### F7.3 — No Password Complexity Validation (P1)
**Evidence**: [api/auth_views.py:51](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/auth_views.py#L51) — only checks `len(password) < 8`. No `AUTH_PASSWORD_VALIDATORS` in Django settings.

**Impact**: Users can register with trivially weak passwords like `12345678` or `password`.

**Recommendation**: Enable Django's built-in `AUTH_PASSWORD_VALIDATORS` (CommonPasswordValidator, MinimumLengthValidator, NumericPasswordValidator, UserAttributeSimilarityValidator).

---

#### F7.4 — Health/Metrics Endpoints Unauthenticated (P1)
**Evidence**: `/api/health/ready/` exposes LLM provider type, Ollama/Groq status, Milvus connection status. `/api/metrics/` exposes Prometheus-format request counts and latency histograms. Both are publicly accessible.

**Impact**: Infrastructure reconnaissance. Attackers can determine technology stack, monitor traffic patterns, and detect when services are degraded (ideal attack windows).

**Recommendation**: Either:
- Put behind authentication for detailed info, return only `{"status": "ok"}` publicly
- Or restrict to internal network / specific IPs

---

#### F7.5 — Error Details Leak Internal State (P1)
**Evidence**: [api/views.py:169](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/views.py#L169) — `"details": str(exc)` in error responses.

**Impact**: Internal exceptions may reveal file paths, connection strings, library versions, or stack traces.

**Recommendation**: Log full details server-side. Return only the classified error message to clients.

---

#### F7.6 — Frontend Feature Flags Overridable via localStorage (P2)
**Evidence**: [feature-flags.ts:34-49](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Frontend/src/lib/feature-flags.ts#L34-L49) — `rag_feature_overrides` in localStorage can enable diagnostics panel, canary features, etc.

**Impact**: Any user can enable admin-only features client-side.

**Recommendation**: Server-side feature flags. Client-side flags should only control UI behavior, never security-sensitive features. The diagnostics panel should require `@jwt_required` + admin role.

---

#### F7.7 — SQLite Database Committed to Repo (P2)
**Evidence**: `db.sqlite3` (180KB) and `milvus_local.db` present in repo root.

**Impact**: Database with user credentials, migration state, and any indexed document metadata is in version control.

**Recommendation**: Remove from tracking: `git rm --cached db.sqlite3 milvus_local.db`. Ensure `.gitignore` covers them.

---

#### F7.8 — CSRF Exempted on All Mutation Endpoints (P2)
**Evidence**: `@csrf_exempt` on `ask_question`, `register`, `login`, `refresh`.

**Impact**: With `CORS_ALLOW_CREDENTIALS=True`, this broadens attack surface. JWT auth provides some protection, but registration and login endpoints have no CSRF or JWT protection.

**Recommendation**: For JWT-authenticated endpoints, CSRF exemption is acceptable. For login/register (pre-auth), implement CSRF protection or use SameSite cookies.

---

## 8. Performance Audit

### 8.1 Findings

#### F8.1 — Embedding Calls Are Synchronous and Blocking (P1)
**Evidence**: All Ollama embedding calls (during ingestion and query) are synchronous. Django processes block waiting for Ollama HTTP responses.

**Impact**: With Gunicorn (3 workers, [Dockerfile.backend](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Dockerfile.backend)), only 3 concurrent queries can be processed. Embedding latency (typically 50-200ms) directly blocks request threads.

**Recommendation**: Use async views with Django 4.1+ `async def` views, or increase Gunicorn workers. Consider caching frequently-queried embeddings.

---

#### F8.2 — BM25 Cache Rebuild Reads All PDFs (P2)
**Evidence**: [Milvus.py:728-738](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L728-L738) — `_refresh_fallback_cache()` loads and chunks ALL PDFs every time.

**Impact**: With 50 PDFs, this could take 30+ seconds. Runs on import and on every cache refresh. Blocks the background thread and holds `_fallback_cache_lock`.

**Recommendation**: Persist BM25 index to disk (pickle/JSON). Rebuild incrementally only when documents change (use content hashes).

---

#### F8.3 — No Query Result Caching (P2)
**Evidence**: No caching layer between API and RAG engine. Every identical question triggers full retrieval + LLM inference.

**Impact**: Repeated questions (common in educational settings) waste compute and increase latency.

**Recommendation**: Add a short-TTL cache (e.g., 5 min) keyed on question hash. Return cached responses for exact matches.

---

#### F8.4 — Neighbor Chunk Expansion Re-reads Corpus (P2)
**Evidence**: [Milvus.py:1465-1509](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/Milvus.py#L1465-L1509) — for BM25 path, neighbor expansion iterates the entire corpus to find adjacent chunks.

**Impact**: O(n) scan of all chunks for each expansion. With 50 PDFs and ~5000+ chunks, this adds noticeable latency.

**Recommendation**: Build a chunk adjacency index (hash map of `(source, page, chunk_index) → chunk`) during cache build.

---

## 9. Evaluation & Benchmarking Review

### 9.1 Current State

| Aspect | Value |
|---|---|
| Golden Set | 3 questions ([eval/golden_set.json](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/eval/golden_set.json)) |
| CI Mode | Mock only (hardcoded answers) |
| Metrics | Keyword hit rate, citation presence |
| Thresholds | 60% keyword, 66% citation, 66% pass rate |

### 9.2 Findings

#### F9.1 — Mock Evaluation Provides Zero Signal (P0)
**Evidence**: [eval/rag_eval.py:24-32](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/eval/rag_eval.py#L24-L32) — `mock_answer()` returns hardcoded strings that are designed to pass. CI only runs mock mode ([.github/workflows/ci.yml:155](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/.github/workflows/ci.yml#L155)).

**Impact**: The evaluation gate is a **rubber stamp**. It has never evaluated actual retrieval or LLM quality. It validates only the harness framework itself. This means:
- Regressions in retrieval quality go undetected
- Prompt changes are never validated
- The golden set has never been tested against the actual system

**Recommendation**:
1. Expand golden set to 20+ questions covering all documents and query types
2. Add a `live` CI job that runs against a test backend with real Milvus + Ollama
3. Add retrieval-specific metrics: Mean Reciprocal Rank (MRR), Precision@k, Recall@k
4. Track metrics over time to detect regressions

---

#### F9.2 — Golden Set Doesn't Cover Actual Corpus (P1)
**Evidence**: The 3 golden questions are generic RAG theory questions ("What is retrieval-augmented generation?"). None reference the actual PDFs in `documents/` (RAG sample 1/2/3.pdf) or test real queries like syllabus lookups, subject inquiries, or curriculum questions.

**Impact**: Even in `live` mode, the golden set wouldn't validate the system's core use case.

**Recommendation**: Create domain-specific golden questions:
- "What are the subjects in semester 3 of CSE?" (curriculum)
- "What is the syllabus of Data Structures?" (subject syllabus)
- "What are the course objectives of Digital Logic Design?" (objectives)
- Include expected source documents and page numbers

---

#### F9.3 — No Retrieval Quality Metrics (P1)
**Evidence**: Only metrics are keyword hit rate and citation presence. No evaluation of whether the correct chunks were retrieved.

**Impact**: Cannot distinguish between: (a) retrieval worked but LLM hallucinated, (b) wrong chunks retrieved, LLM faithfully reproduced garbage.

**Recommendation**: Separate retrieval evaluation from generation evaluation:
- **Retrieval**: Was the correct source document retrieved? Was the correct page/unit retrieved? (Precision@k, Recall@k)
- **Generation**: Does the answer contain expected keywords? Is it factually consistent with the context? (keyword hit rate, ROUGE, BERTScore)

---

## 10. Infrastructure & Deployment Review

### 10.1 Findings

#### F10.1 — Non-Reproducible Builds (P0)
**Evidence**: [requirements_django.txt](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/requirements_django.txt) uses `>=` version pins. Django is completely unpinned. No `pip freeze` lock file. Frontend has `bun.lockb` and `package-lock.json` (multiple package managers).

**Impact**: Two installs of the same requirements can produce different dependency trees. LangChain's rapid versioning makes this especially dangerous — a minor version bump can change behavior.

**Recommendation**:
1. Pin exact versions: `Django==5.1.5`, `langchain==0.3.x`, etc.
2. Generate `requirements.lock` via `pip-tools` or `pip freeze`
3. Standardize on one frontend package manager (npm) and delete `bun.lockb`
4. Use `pip install --require-hashes` for supply chain security

---

#### F10.2 — Duplicate Root-Level Frontend (P2)
**Evidence**: Root `package.json` has `vite ^5.4.19`, Frontend `package.json` has `vite ^7.3.1`. Root `src/` directory exists alongside `Frontend/src/`. AGENTS.md acknowledges root `src/` is legacy.

**Impact**: Contributors may accidentally edit the wrong frontend. CI may install wrong dependencies. Version conflicts between root and Frontend.

**Recommendation**: Delete root-level `package.json`, `vite.config.ts`, `vitest.config.ts`, `tsconfig.json`, `src/`, and related files. Keep only `Frontend/`.

---

#### F10.3 — Docker Compose Missing Critical Components (P1)
**Evidence**: [docker-compose.prod.yml](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/docker-compose.prod.yml):
- Hardcoded Postgres credentials (line 27-29)
- No Milvus service (relies on external cloud)
- No nginx reverse proxy
- No healthcheck directives
- No Ollama service

**Impact**: Cannot deploy the full stack with `docker-compose up`. Contradicts on-premise strategy.

**Recommendation**: Add to docker-compose:
- Milvus Lite or Milvus Standalone service
- Ollama service
- nginx reverse proxy for unified routing
- Healthchecks on all services
- Environment variable references instead of hardcoded credentials

---

#### F10.4 — No Logging Aggregation or Monitoring (P2)
**Evidence**: Metrics are in-memory only ([api/metrics.py](file:///c:/Sabareesh/Visual%20Studio%20Code/AcademeRAG/AcademeRAG-Final/api/metrics.py)). No Prometheus client library. No log shipping. No alerting.

**Impact**: In production, you cannot diagnose issues after restart (metrics lost). No visibility into retrieval quality degradation over time.

**Recommendation**: For on-premise:
- Use `prometheus_client` Python library for persistent metrics
- Add structured JSON logging
- Consider Loki + Grafana for log aggregation (lightweight, self-hosted)

---

#### F10.5 — Bundle Budget Inconsistency (P3)
**Evidence**: CI sets `VITE_MAX_JS_BUNDLE_KB=600`, Playwright config hardcodes 550, `.env.example` says 600, `check-bundle-budget.mjs` defaults to 550.

**Recommendation**: Centralize to one value in one place. Read from `package.json` config.

---

#### F10.6 — manage.py Has Dead Code (P3)
**Evidence**: Lines 1-23 are a triple-quoted string (commented-out code). Lines 25-43 are the real implementation.

**Recommendation**: Delete lines 1-23.

---

## 11. Production Readiness Summary

### Scorecard

| Domain | Score | Assessment |
|---|---|---|
| RAG Architecture | 4/10 | Monolithic, cloud-dependent, excessive complexity |
| Retrieval Quality | 3/10 | Hardcoded bypasses, no re-ranking, heuristic-driven |
| Hybrid Search | 2/10 | Fallback-only, not true hybrid |
| Chunking & Embedding | 3/10 | Structure-unaware, no metadata enrichment |
| Vector Database | 4/10 | Cloud contradicts strategy, no scalar indexes |
| LLM Response Quality | 5/10 | Decent prompt, but no citations, high temperature |
| Security | 4/10 | Good JWT + CORS config, but leaked secrets, silent rate limit degradation |
| Performance | 4/10 | No caching, synchronous blocking, full corpus scans |
| Evaluation | 1/10 | Mock-only eval, 3 generic questions, zero real signal |
| Infrastructure | 3/10 | Non-reproducible builds, incomplete Docker, no monitoring |

**Overall Production Readiness: 3.3/10 — NOT READY FOR PRODUCTION**

---

## Implementation Roadmap

### Phase 1: Critical Fixes (P0 — Must Do First)

> [!CAUTION]
> These issues will cause data loss, security breaches, or complete system failures in production.

| ID | Finding | Effort |
|---|---|---|
| F7.1 | Rotate secrets, remove `.env` from git history | 2h |
| F7.2 | Make rate limiting a hard dependency | 1h |
| F5.1 | Switch to Milvus Lite for on-premise | 4h |
| F2.1 | Remove hardcoded curriculum bypass | 1h |
| F9.1 | Build real golden set + live eval | 8h |
| F10.1 | Pin all dependency versions, create lock files | 3h |
| F1.2 | Remove all Groq dead code | 3h |

**Estimated Phase 1**: ~22 hours

---

### Phase 2: Retrieval Quality (P1 — Before Production)

> [!IMPORTANT]
> These issues will cause incorrect answers, poor user experience, or reliability problems.

| ID | Finding | Effort |
|---|---|---|
| F4.1 | Implement structure-aware chunking | 8h |
| F4.2 | Add metadata enrichment during ingestion | 6h |
| F2.2 | Replace hardcoded scoring with metadata-based approach | 4h |
| F2.3 | Route syllabus extraction through LLM | 2h |
| F6.2 | Add structured context assembly with source markers | 2h |
| F6.4 | Lower default temperature to 0.1 | 0.5h |
| F6.1 | Add citation instructions to prompt | 1h |
| F1.5 | Move module-level side effects to explicit startup | 2h |

**Estimated Phase 2**: ~25.5 hours

---

### Phase 3: Security Hardening (P1-P2)

| ID | Finding | Effort |
|---|---|---|
| F7.3 | Enable Django password validators | 1h |
| F7.4 | Protect health/metrics endpoints | 2h |
| F7.5 | Remove error detail leaks | 1h |
| F7.6 | Server-side feature flags | 3h |
| F7.7 | Remove SQLite/Milvus DB from git | 0.5h |
| F7.8 | CSRF protection for pre-auth endpoints | 2h |

**Estimated Phase 3**: ~9.5 hours

---

### Phase 4: Architecture & Performance (P2)

| ID | Finding | Effort |
|---|---|---|
| F1.1 | Decompose Milvus.py into modules | 8h |
| F1.3 | Convert to proper Python package | 2h |
| F1.4 | Guard hot-reload behind DEBUG | 0.5h |
| F3.1 | Implement RRF hybrid search | 6h |
| F3.2 | Improve BM25 tokenization | 3h |
| F2.4 | Add re-ranking stage | 4h |
| F8.1 | Query result caching | 3h |
| F8.2 | Persist BM25 index to disk | 3h |
| F8.3 | Query result caching | 3h |
| F8.4 | Build chunk adjacency index | 2h |
| F10.2 | Delete duplicate root frontend | 1h |
| F10.3 | Complete Docker Compose for on-premise | 4h |

**Estimated Phase 4**: ~39.5 hours

---

### Phase 5: Production Hardening (P2-P3)

| ID | Finding | Effort |
|---|---|---|
| F2.5 | Fix threshold behavior, add hard floor | 1h |
| F2.6 | Query preprocessing pipeline | 4h |
| F5.2 | Add scalar indexes on metadata fields | 1h |
| F5.3 | Reduce VARCHAR max_length | 0.5h |
| F6.3 | Context length cap | 1h |
| F9.2 | Expand golden set to 20+ domain questions | 4h |
| F9.3 | Separate retrieval vs generation metrics | 4h |
| F10.4 | Logging aggregation + monitoring | 6h |
| F10.5 | Centralize bundle budget | 0.5h |
| F10.6 | Clean manage.py dead code | 0.5h |
| F4.3 | PDF extraction quality validation | 3h |
| F4.4 | Cache embedding dimensions | 0.5h |

**Estimated Phase 5**: ~26 hours

---

## User Review Required

> [!IMPORTANT]
> **Phase priority**: Do you agree with the phase ordering? Phase 1 (critical fixes) and Phase 2 (retrieval quality) are the highest impact. Should any findings be reprioritized?

> [!IMPORTANT]
> **Milvus Lite migration**: Switching from Zilliz Cloud to Milvus Lite (F5.1) is a significant change. This means all data is stored locally in a file. Are you comfortable with this for on-premise deployment?

> [!IMPORTANT]
> **Groq removal**: Removing all Groq code (F1.2) is irreversible without re-implementation. Confirm that self-hosted Ollama is the definitive LLM strategy.

> [!WARNING]
> **Total estimated effort**: ~122 hours across all 5 phases. Phase 1+2 alone (~47.5 hours) would bring the system to a minimally viable production state. Do you want me to proceed with Phase 1 first?

## Open Questions

1. **Which Ollama model** are you using for embeddings and LLM? (e.g., `nomic-embed-text`, `llama3.2`, `mistral`)
2. **Are there additional PDFs** beyond the current 3 that should be included in the golden set?
3. **Is there an existing staging/test environment**, or should all testing happen on the development machine?
4. **Do you have user accounts** in the current SQLite database that need to be preserved, or can we start fresh?
