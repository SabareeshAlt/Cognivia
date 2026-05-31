# AcademeRAG — Full Audit, Refactor & Re-Index Implementation Plan

## Background

A complete read-only audit of the `AcademeRAG-Final` repository was performed covering:
- All Python source files, configuration, and dependencies
- The `rag/` module structure and its refactor state
- The monolithic `Milvus.py` engine (2,114 lines)
- Current Zilliz Cloud collection state and vector contents
- Embedding dimensions and model alignment
- Frontend organization
- Clutter, artifacts, and tracked-but-ignored files

---

## 1. What Was Found

### Model Configuration (Current State in `.env`)
| Setting | Current Value |
|---|---|
| `EMBEDDING_MODEL` | `mxbai-embed-large` |
| `ACADEMERAG_LLM_MODEL` | `gemma3:12b` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` |
| `COLLECTION_NAME` | `AcademeRAG` |
| `ACADEMERAG_MILVUS_URI` | Zilliz Cloud (serverless, AWS eu-central-1) |

**Embedding dimension confirmed: `mxbai-embed-large` → 1024 dims.**
**Zilliz Cloud collection schema: vector dim = 1024. Aligned.**

---

### Zilliz Cloud Collection — Current State (CRITICAL PROBLEM)

> [!CAUTION]
> The cloud collection `AcademeRAG` currently has **3,891 vectors** indexed from **4 stale PDF files** that no longer exist in the repository.

| Source Indexed | Chunks | Status |
|---|---|---|
| `RAG sample 1.pdf` (old, small) | 292 | STALE — wrong version |
| `RAG sample 2.pdf` (old, small) | 413 | STALE — wrong version |
| `RAG sample 3.pdf` | 518 | STALE — file deleted from repo |
| `RAG sample 4.pdf` | 2,668 | STALE — file does not exist locally |

The **current 2 large PDFs** in `documents/` (~959 and ~1151 pages respectively) have **NOT been indexed at all**. Every query against the cloud collection returns results from old, stale, or non-existent documents.

---

### Refactor Audit — `rag/` Module (INCOMPLETE REFACTOR)

> [!WARNING]
> The previous refactor that was supposed to split `Milvus.py` into smaller `rag/` modules was **never completed**. All 14 module stub files contain only 3 lines of placeholder comments.

| File | Size | Status |
|---|---|---|
| `rag/bm25.py` | 54 bytes | **Empty stub** — 3-line placeholder only |
| `rag/chunking.py` | 58 bytes | **Empty stub** |
| `rag/config.py` | 56 bytes | **Empty stub** |
| `rag/retrieval.py` | 59 bytes | **Empty stub** |
| `rag/hybrid_search.py` | 63 bytes | **Empty stub** |
| `rag/ingestion.py` | 59 bytes | **Empty stub** |
| `rag/llm.py` | 53 bytes | **Empty stub** |
| `rag/reranker.py` | 58 bytes | **Empty stub** |
| `rag/cache.py` | 55 bytes | **Empty stub** |
| `rag/metadata.py` | 58 bytes | **Empty stub** |
| `rag/prompts.py` | 57 bytes | **Empty stub** |
| `rag/evaluation.py` | 60 bytes | **Empty stub** |
| `rag/utils.py` | 55 bytes | **Empty stub** |
| `rag/llm_orchestration.py` | 27KB | **ACTIVE** — full production code |
| `rag/scoring.py` | 7KB | **ACTIVE** — full production code |
| `rag/pdf_sandbox.py` | 2.7KB | **ACTIVE** — full production code |

**Reality**: All retrieval, BM25, chunking, ingestion, and embedding logic lives exclusively in the 2,114-line `Milvus.py` root file. The `rag/` stubs are dead weight that create an illusion of modularization that doesn't exist.

---

### Clutter Analysis

#### Files Safe to Delete
| File/Dir | Reason |
|---|---|
| `rag/bm25.py` | Empty stub — code lives in `Milvus.py` |
| `rag/chunking.py` | Empty stub |
| `rag/config.py` | Empty stub |
| `rag/retrieval.py` | Empty stub |
| `rag/hybrid_search.py` | Empty stub |
| `rag/ingestion.py` | Empty stub |
| `rag/llm.py` | Empty stub |
| `rag/reranker.py` | Empty stub |
| `rag/cache.py` | Empty stub |
| `rag/metadata.py` | Empty stub |
| `rag/prompts.py` | Empty stub |
| `rag/evaluation.py` | Empty stub |
| `rag/utils.py` | Empty stub |
| `setup_milvus.py` | Redundant — superseded by `create_milvus_collection.py` |
| `test_query.py` | Root-level ad-hoc test, unstructured, not in test suite |
| `verify_query.py` | Root-level ad-hoc test, unstructured, not in test suite |
| `vitest.config.ts` (root) | Duplicate — the real one lives in `Frontend/vitest.config.ts` |
| `eslint.config.js` (root) | Duplicate — the real one lives in `Frontend/eslint.config.js` |
| `Consequences.txt` | Personal development diary, not codebase-related |
| `WINDOWS_RUN_GUIDE.md` | Superseded by `README.md` which already covers this |
| `FINAL_PROJECT_STRUCTURE.md` | Now stale (describes `Plan/` which is gone) |
| `ARCHITECTURE_DIAGRAMS.md` | Optional: review for accuracy, may be kept |
| `bm25_index.pkl` | Runtime artifact — gitignored but still present, should be excluded |
| `bm25_index.pkl.build.lock` | Runtime lock file — should be excluded |
| `scratch/` | Dev scratchpad — already gitignored; clean from working tree |
| `Plan/` (directory) | Already emptied — remove from fs entirely |
| `__pycache__/` (root) | Runtime bytecode — should be gitignored and excluded |
| `api/migrations/__pycache__/` | Compiled migration bytecode — should be gitignored |
| `rag_project/__pycache__/` | Compiled bytecode — should be gitignored |
| `prometheus_multiproc_dir/` | Runtime metrics storage — should be excluded |
| `static/js/rag-client.js` | Legacy standalone JS client — not used by React frontend |

#### Files to Keep
| File | Reason |
|---|---|
| `Milvus.py` | Core RAG engine — all live code |
| `main.py` | Unified startup launcher |
| `manage.py` | Django management |
| `create_milvus_collection.py` | Official ingestion CLI |
| `api/` | Django REST backend |
| `rag/llm_orchestration.py` | Active LLM routing and streaming |
| `rag/scoring.py` | Active pipeline scoring |
| `rag/pdf_sandbox.py` | Active sandboxed PDF reader |
| `rag_project/` | Django project config |
| `Frontend/` | React/Vite frontend |
| `eval/` | RAG evaluation harness |
| `documents/` | PDF corpus |
| `docs/openapi.yaml` | API spec |
| `.github/workflows/` | CI pipelines |
| `AGENTS.md` | Coding guidelines |
| `README.md` | Main documentation |
| `RAG_SCORING_REPORT.md` | Active scoring documentation |
| `IMPLEMENTATION_REPORT.md` | Engineering history |
| `requirements_django.txt` | Primary dependency manifest |
| `docker-compose.prod.yml` | Container orchestration |
| `Dockerfile.backend` / `Dockerfile.frontend` | Container builds |
| `.coveragerc` | Test coverage config |

#### Needs Review / Careful Decision
| File | Issue |
|---|---|
| `ARCHITECTURE_DIAGRAMS.md` | Large (28KB) — verify if diagrams are still accurate |
| `scripts/secure_repo.sh` | Single-line bash — verify if still needed |
| `Frontend/test-results/` | Playwright test artifacts — should be gitignored |
| `api/settings.py` | Separate settings from `rag_project/settings.py` — confirm purpose |

---

### Frontend Audit
- `Frontend/` is well-organized: `src/components/`, `src/pages/`, `src/store/`, `src/lib/`, `src/hooks/`
- No misplaced backend code detected
- `node_modules/`, `dist/`, `coverage/`, `playwright-report/` are gitignored
- `Frontend/test-results/` has `.last-run.json` committed — should be cleaned
- One issue: `eslint.config.js` and `vitest.config.ts` exist **both** at the repo root and inside `Frontend/` — the root copies are duplicates/stale

### Backend Audit
- Django app is in `api/` and project config in `rag_project/`
- No separate `backend/` folder exists — the flat root layout mixes backend and RAG engine files
- `api/settings.py` (1.8KB) appears to be a separate settings fragment — not the main settings

---

## 2. What Files I Recommend Removing

### Definitive Safe Deletes (13 empty `rag/` stubs + 12 root clutter files)
```
rag/bm25.py
rag/chunking.py
rag/config.py
rag/retrieval.py
rag/hybrid_search.py
rag/ingestion.py
rag/llm.py
rag/reranker.py
rag/cache.py
rag/metadata.py
rag/prompts.py
rag/evaluation.py
rag/utils.py
setup_milvus.py
test_query.py
verify_query.py
vitest.config.ts  (root level only)
eslint.config.js  (root level only)
Consequences.txt
WINDOWS_RUN_GUIDE.md
FINAL_PROJECT_STRUCTURE.md
static/js/rag-client.js
Frontend/test-results/.last-run.json
Plan/  (already emptied directory)
```

### Runtime Artifacts to Purge and Add to `.gitignore`
```
bm25_index.pkl
bm25_index.pkl.build.lock
__pycache__/  (root)
api/migrations/__pycache__/
rag/__pycache__/
rag_project/__pycache__/
prometheus_multiproc_dir/
scratch/  (contents — already gitignored)
```

---

## 3. How I Will Reorganize Folders

The project layout will remain **mostly flat** — the Django and RAG code are deeply intertwined at the root level. A full folder-level reorganization (adding `backend/`, `milvus/` directories) would require updating dozens of import paths in `Milvus.py`, `rag/llm_orchestration.py`, `api/views.py`, `create_milvus_collection.py`, and `main.py`. This carries high breakage risk with zero functional gain.

**Instead, the reorganization will be:**

1. **Clean empty stubs** from `rag/` — turning the module from a facade of false modularity into a small, honest set of 3 real active files
2. **Remove root clutter** — duplicate configs, stale guides, personal notes
3. **Add a proper `milvus/` documentation folder** (not a code folder) with Zilliz connection notes and schema reference — no code migration needed
4. **Harden `.gitignore`** to exclude all runtime artifacts that have crept into the tracked files

### Proposed Final Clean Structure
```
AcademeRAG-Final/
├── .github/workflows/          # CI and security pipelines
├── api/                        # Django REST app (auth, views, metrics, rate limit)
│   ├── migrations/
│   └── *.py
├── documents/                  # PDF corpus (the 2 large PDFs)
│   ├── RAG sample 1.pdf        # ~959 pages
│   └── RAG sample 2.pdf        # ~1151 pages
├── docs/openapi.yaml           # OpenAPI spec
├── eval/                       # RAG evaluation harness + golden sets
├── Frontend/                   # React + Vite + TypeScript (unchanged)
├── rag/                        # Active RAG modules only (3 files)
│   ├── __init__.py
│   ├── llm_orchestration.py    # Groq/Ollama router + streaming
│   ├── pdf_sandbox.py          # Multiprocess sandboxed PDF reader
│   └── scoring.py              # Pipeline scoring engine
├── rag_project/                # Django project config
├── scripts/                    # Admin scripts
├── .coveragerc
├── .env                        # Local env (not committed)
├── .gitignore                  # Updated
├── AGENTS.md
├── ARCHITECTURE_DIAGRAMS.md
├── create_milvus_collection.py # Ingestion CLI
├── docker-compose.prod.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── IMPLEMENTATION_REPORT.md
├── main.py                     # Startup launcher
├── manage.py
├── Milvus.py                   # Core RAG engine (2114 lines)
├── RAG_SCORING_REPORT.md
├── README.md
├── requirements.txt
└── requirements_django.txt
```

---

## 4. What Will Happen with Milvus

### Local Milvus (Milvus Lite)
- Stored at `milvus_local.db/` in the project root
- Used as **automatic fallback** when Zilliz Cloud search returns 0 results
- The dense search pipeline (`_dense_search_pipeline`) tries Cloud first, then falls back to local
- The local collection will be **rebuilt** as part of ingestion using the new PDFs

### Zilliz Cloud (Primary)
- URI: `https://in03-200a60c94a793fc.serverless.aws-eu-central-1.cloud.zilliz.com`
- Collection: `AcademeRAG`
- **Current state: 3,891 stale vectors from 4 non-existent PDFs — MUST BE PURGED**
- The collection will be **dropped and recreated** with identical schema (vector dim=1024, COSINE metric, AUTOINDEX)
- Fresh ingestion of the 2 current PDFs (~2300 pages total) will produce an estimated **10,000–18,000 new chunks** (at chunk_size=1000, overlap=200)

> [!IMPORTANT]
> The collection drop is **non-destructive to your data** — the source PDFs are safely stored in `documents/`. A fresh, accurate index will be built from the correct documents.

### What Collections Will Be Updated
| Location | Action |
|---|---|
| Zilliz Cloud `AcademeRAG` | Drop + recreate + full re-ingest |
| Local `milvus_local.db` | Rebuild from same chunked docs |
| BM25 index `bm25_index.pkl` | Rebuilt at startup automatically |

---

## 5. What Will Happen with the Two PDFs

### Parsing
- Each PDF is read via `rag/pdf_sandbox.py` — a `multiprocessing` isolated worker using `pypdf.PdfReader`
- Timeout increased to **180 seconds** per PDF (already in place for the large docs)
- Magic-byte + MIME validation is performed before processing
- **PDF 1**: ~959 pages → estimated 2,400–4,000 chunks
- **PDF 2**: ~1,151 pages → estimated 3,000–5,000 chunks

### Chunking
- `RecursiveCharacterTextSplitter`: `chunk_size=1000`, `chunk_overlap=200`
- Structure-aware: section boundaries (UNIT I, II, etc.) trigger explicit flushes
- Page numbers, unit numbers, section types, and document hashes are preserved in metadata

### Embedding
- Model: **`mxbai-embed-large:latest`** via Ollama at `http://localhost:11434`
- Output dimension: **1024** (confirmed)
- Each chunk text is embedded individually before batch insertion

### Ingestion
- Batch size: 16 chunks per Milvus insert call (controlled by `INGEST_BATCH_SIZE`)
- Timeout: 1800 seconds (30 min) for the full ingestion run (`INGEST_MAX_SECONDS`)
- Progress logged every batch: `% complete | elapsed | eta`

### Storage and Retrieval
- Primary: Zilliz Cloud — COSINE similarity, AUTOINDEX
- Fallback: Local Milvus Lite
- Metadata fields stored per chunk: `source`, `page_number`, `chunk_index`, `document_hash`, `subject_name`, `unit_number`, `unit_title`, `section_type`
- Scalar INVERTED indexes on `source`, `page_number`, `chunk_index` for fast metadata filtering

### Retrieval Pipeline
1. Parallel: Dense (Zilliz Cloud → Local fallback) + BM25 (in-memory from pkl)
2. RRF fusion of both result sets
3. Cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
4. Neighbor expansion (±1 adjacent chunk for continuity)
5. Context formatted with token budget (tiktoken cl100k_base, 32K char limit)

---

## 6. Model Configuration

| Component | Model | Location |
|---|---|---|
| **Embeddings** | `mxbai-embed-large:latest` | Ollama @ `http://localhost:11434` |
| **Answer Generation** | `gemma3:12b` | Ollama @ `http://localhost:11434` (offline primary) |
| **Online Fallback** | Groq `llama-3.3-70b-versatile` | Groq API (if `GROQ_API_KEY` set + internet available) |
| **Cross-encoder Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | HuggingFace (sentence-transformers) |

> [!IMPORTANT]
> The `.env` already has `ACADEMERAG_LLM_MODEL=gemma3:12b` and `EMBEDDING_MODEL=mxbai-embed-large` configured. No code changes are required for model selection — these are already correct.

---

## 7. Risks

### Indexing Risks
| Risk | Mitigation |
|---|---|
| Large PDF parsing timeout (~1150 pages) | 180s per-PDF sandbox timeout already in place |
| Ingestion timeout on 10K+ chunks | `INGEST_MAX_SECONDS=1800` (30 min) — sufficient |
| Zilliz Cloud API rate limit during batch insert | `INGEST_BATCH_SIZE=16` keeps insert rate conservative |
| Ollama unresponsive during embedding | Embedding call wrapped with error handling; will abort cleanly |

### Performance Risks
| Risk | Mitigation |
|---|---|
| BM25 rebuild of ~15K chunks at startup | Persisted to `bm25_index.pkl`; rebuilt once, reloaded on restart |
| Memory pressure with ~15K chunk corpus in RAM | Typical corpus at 1K chars/chunk ≈ 15MB — within safe range |
| Large context window (32K chars) straining gemma3:12b | Context truncated at sentence boundary; token budget enforced |

### Retrieval Risks
| Risk | Mitigation |
|---|---|
| Semantic search accuracy on 2300-page academic corpus | Cross-encoder reranking + neighbor expansion compensates for embedding recall gaps |
| Stale BM25 index after re-ingest | Signature check at startup forces rebuild when PDF hash changes |
| Duplicate vectors if re-ingest runs twice | Collection is **dropped and recreated** — no duplicate risk |

### Accuracy Risks
| Risk | Mitigation |
|---|---|
| gemma3:12b hallucinating beyond retrieved context | System prompt strictly prohibits fabrication; `answer_grounding_score` flags hallucinations |
| Citation mismatch | Citation confidence score validates citations against retrieved metadata |
| Query routing to wrong PDF | Source-specific query detection (`_extract_target_sources`) + metadata filtering |

---

## 8. Implementation Steps (After Approval)

### Step 1 — Repository Cleanup
- Delete 13 empty `rag/` stubs
- Delete root duplicate configs and clutter files
- Update `.gitignore` for all runtime artifacts
- Commit cleanup

### Step 2 — Zilliz Cloud Collection Rebuild
- Run `create_milvus_collection.py --recreate` to drop and recreate `AcademeRAG`
- Verify collection schema (dim=1024, COSINE, AUTOINDEX, scalar indexes)

### Step 3 — Full PDF Ingestion
- Parse both PDFs through sandbox extractor
- Chunk with RecursiveCharacterTextSplitter (1000/200)
- Embed each chunk with `mxbai-embed-large` (dim=1024)
- Insert to Zilliz Cloud in batches of 16
- Also sync local Milvus Lite
- Rebuild BM25 index from same chunks
- Log per-source chunk counts for verification

### Step 4 — Retrieval Verification
- Run probe queries against both PDFs
- Verify cross-PDF retrieval (questions about content spanning both documents)
- Verify citation metadata (source filename, page number) is accurate
- Check RAG score output (target: retrieval_relevance > 60, grounding > 70)

### Step 5 — Commit and Push
- Commit cleaned repo + updated docs
- Push to `main` on `https://github.com/P-Sakthi-Sabareesh/AcademeRAG-Final.git`

---

## Open Questions

> [!IMPORTANT]
> **Do you want to keep `ARCHITECTURE_DIAGRAMS.md` (28KB)?**
> It was useful history but may now be inaccurate given the changes. Options: keep as-is, update it, or delete it.

> [!IMPORTANT]
> **Ingestion duration estimate**: With ~2300 pages → ~15,000 chunks and Ollama embedding at roughly 5–15 chunks/second locally, full ingestion will take **15–50 minutes** depending on your hardware. Is this acceptable, or should we increase batch size?

> [!IMPORTANT]
> **Groq API key**: The `.env` does not have `GROQ_API_KEY` set. The system will run fully offline via `gemma3:12b`. This is fine — just confirming this is intentional.

---

# This is the complete implementation plan I propose. Do you approve proceeding?
