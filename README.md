# AcademeRAG-Final

AcademeRAG-Final is a full-stack Retrieval-Augmented Generation (RAG) platform for academic question answering. It combines a Django API backend, a React/Vite frontend, and a Milvus-based retrieval layer with provider-routed LLM generation. The current implementation is local-first for reliability, supports full offline operation on the local machine, and prefers Groq for answer generation when online.

## What This Project Does

- Authenticates users with JWT access/refresh tokens.
- Accepts user questions through REST and streaming endpoints.
- Retrieves relevant document chunks from Milvus/Zilliz when available, with an improved local fallback retriever when cloud retrieval is unavailable.
- Generates grounded responses with Groq-first routing and local Ollama fallback.
- Supports syllabus/unit-wise extraction directly from uploaded PDFs for long academic syllabus queries.
- Exposes health, readiness, metrics, and admin diagnostics endpoints.

## Current Stack

- Backend: Django, Django REST Framework, SimpleJWT, django-ratelimit, django-cors-headers
- Retrieval: LangChain, Milvus (local file or Zilliz Cloud), PyPDF ingestion
- LLM/Embeddings: Groq (OpenAI-compatible endpoint) + Ollama fallback, Ollama embeddings
- Frontend: React + TypeScript + Vite + Radix/shadcn components + Zustand
- Quality/Security: Vitest, Playwright, coverage gates, Bandit, pip-audit, npm audit, SBOM generation

## Repository Layout

- `main.py`: Unified local launcher (backend + frontend)
- `manage.py`: Django management commands
- `rag_project/`: Django project settings and URL config
- `api/`: Auth endpoints, ask/stream endpoints, health, metrics, middleware
- `Milvus.py`: Primary retrieval and response pipeline integration
- `create_milvus_collection.py`: Collection creation/reindex flow
- `Frontend/`: Main React frontend used by launcher and CI
- `documents/`: PDF source corpus for ingestion
- `eval/`: RAG evaluation gate scripts and reports
- `.github/workflows/`: CI and security pipelines

## Runtime Architecture

1. User logs in via `/api/auth/login/`.
2. Frontend stores tokens and sends authenticated requests.
3. `/api/ask/` or `/api/ask/stream/` receives question.
4. Backend loads retrieval/generation functions from `Milvus.py` lazily.
5. Retrieval tries Milvus Cloud first when healthy; otherwise it routes to the cached local fallback retriever.
6. Syllabus/unit-wise queries can bypass the LLM and return cleaned text extracted directly from the PDF pages.
7. Generation composes final answer and returns JSON or stream chunks.

## Environment Configuration

Configuration is environment-first and validated at startup.

Core variables include:

- `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`
- `DB_ENGINE` (`sqlite` or `postgres`) and postgres variables when needed
- `CORS_ALLOW_ALL_ORIGINS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`
- `JWT_ACCESS_MINUTES`, `JWT_REFRESH_DAYS`
- `RATELIMIT_DEFAULT`, `AUTH_REGISTER_RATELIMIT`, `AUTH_LOGIN_RATELIMIT`, `AUTH_REFRESH_RATELIMIT`
- `OLLAMA_HEALTHCHECK_URL`
- `ACADEMERAG_LLM_PROVIDER` (`ollama` or `groq`)
- `GROQ_API_KEY`, `GROQ_BASE_URL`, `ACADEMERAG_GROQ_MODEL`
- `ACADEMERAG_GROQ_TIMEOUT_SECONDS`
- `ACADEMERAG_MILVUS_URI`, `ACADEMERAG_MILVUS_TOKEN`, `COLLECTION_NAME`
- `EMBEDDING_MODEL`, `ACADEMERAG_LLM_MODEL`, `ACADEMERAG_TOP_K`
- `ACADEMERAG_MILVUS_TIMEOUT_SECONDS`
- `ACADEMERAG_MILVUS_INIT_TIMEOUT_SECONDS`
- `ACADEMERAG_MILVUS_HEALTHCHECK_TIMEOUT_SECONDS`
- `ACADEMERAG_MILVUS_CIRCUIT_BREAKER_SECONDS`
- `CHUNK_SIZE`, `CHUNK_OVERLAP`

Use `.env.example` as the reference template.

## Local Development

### 1) Install backend dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Install frontend dependencies

```bash
cd Frontend
npm ci
cd ..
```

### 3) Start both services

```bash
python3 main.py
```

Default local URLs:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

You can also run separately:

```bash
python3 manage.py runserver 127.0.0.1:8000
cd Frontend && npm run dev
```

## Document Ingestion

- Put PDF files in `documents/`.
- Run controlled collection setup/rebuild:

```bash
python3 create_milvus_collection.py --recreate-safe
```

- Convenience setup script is available:

```bash
python3 setup_milvus.py
```

## Chat UX Behavior

- Streaming responses can be stopped mid-generation using the stop button in chat.
- Sending a new message while streaming interrupts the in-flight response and starts the new request.
- Assistant messages are rendered as sanitized markdown (headings, lists, code blocks, links, inline emphasis).
- Chat threads persist across logout/login on the same browser profile.
- Chat input is no longer blocked just because the browser reports offline; local backend usage is still allowed when the machine is offline.
- Ordered lists in markdown continue sequential numbering across adjacent list blocks.
- Paragraph-style answers preserve visible paragraph separation.

## LLM Routing

- `ACADEMERAG_LLM_PROVIDER=groq` routes generation to Groq first.
- If Groq is enabled and unavailable, fallback to Ollama occurs only when Ollama is reachable.
- `GROQ_BASE_URL` must be the API endpoint (`https://api.groq.com/openai/v1`), not the Groq Console URL.
- Groq reachability is handled during the actual generation request; the backend no longer pre-probes `/models` before answering.

## Retrieval Behavior

- Online retrieval uses Milvus/Zilliz when the cloud endpoint is healthy.
- Offline retrieval uses the local cached fallback retriever over the PDF corpus.
- The fallback retriever is BM25-style over cached PDF chunks and is substantially stronger than a simple token-overlap fallback.
- Page-aware metadata is preserved for locally parsed PDFs.
- Neighbor chunk expansion is used to retain continuity for multi-part answers.
- Syllabus and unit-wise queries use a dedicated extraction path to reduce summarization loss and incomplete answers.

## Offline and Online Modes

- Offline:
  - frontend remains usable
  - retrieval uses the local PDF corpus
  - generation uses local Ollama when available
- Online:
  - Groq is preferred for answer generation
  - Milvus Cloud is preferred for retrieval when healthy
  - local retrieval remains the automatic backup path if cloud retrieval is unhealthy

## Milvus Failover and Performance Controls

- Milvus reachability is checked with a short health check before expensive sync work starts.
- Milvus initialization timeout is lower than the previous implementation to fail fast when the endpoint is unreachable.
- A circuit breaker suppresses repeated slow cloud retries when Milvus is temporarily unhealthy.
- Local corpus parsing/chunking is cached and refreshed in the background where possible to keep request latency down.
- Collection lifecycle handling now waits for collection drop/create visibility before use, which stabilizes Zilliz Cloud rebuilds.

## API Endpoints

Auth:

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/`

RAG:

- `POST /api/ask/`
- `POST /api/ask/stream/`

Ops:

- `GET /api/health/live/`
- `GET /api/health/ready/`
- `GET /api/health/` (compat alias)
- `GET /api/metrics/`
- `GET /api/admin/retrieval/diagnostics/` (staff/superuser)

## Testing and Quality Gates

Backend:

```bash
python3 manage.py check
python3 manage.py test
```

Frontend:

```bash
cd Frontend
npm run lint
npm run test
npm run test:coverage
npm run build
npm run perf:budget
npm run test:e2e
```

CI (`.github/workflows/ci.yml`) enforces:

- Django checks + backend coverage floor
- Frontend lint/test/coverage/build
- Bundle budget check
- Playwright E2E
- RAG evaluation regression gate (`eval/rag_eval.py`)

Security workflow (`.github/workflows/security-supply-chain.yml`) enforces:

- Secret scanning (Gitleaks)
- Backend audits (`pip-audit`, `bandit`)
- Frontend `npm audit`
- SBOM generation for backend/frontend

## Latest Implemented Changes

- Integrated and hardened JWT auth flow with register/login/refresh/me endpoints.
- Added rate limiting controls for auth and question endpoints.
- Added request ID middleware and structured logging formatters/filters.
- Added readiness/liveness/metrics endpoints and dependency-aware readiness checks.
- Connected API retrieval path to `Milvus.py` lazy-loading flow.
- Added admin-only retrieval diagnostics endpoint.
- Added frontend API client resilience:
  - timeout handling
  - retry on transient failures
  - local API port failover probing
- Added frontend feature flag resolution and canary bucketing.
- Added CI gates for backend/frontend tests, coverage, bundle budget, E2E.
- Added security and supply-chain workflow with audits and SBOM output.
- Added RAG evaluation gate in CI using `eval/rag_eval.py`.
- Added Groq provider integration with runtime provider failover in `Milvus.py`.
- Added Groq/Ollama-aware readiness reporting in `api/views.py`.
- Added streaming interruption controls and markdown rendering in `Frontend/src/pages/ChatPage.tsx`.
- Fixed chat thread persistence across auth flows by preserving persisted chat state.
- Removed the frontend hard block on offline browser mode so localhost usage still works without internet.
- Improved local retrieval with a BM25-style cached fallback retriever over PDF chunks.
- Added page-aware PDF metadata and neighbor-chunk expansion to improve long-answer continuity.
- Added syllabus/unit query extraction directly from PDF page text to avoid LLM truncation on long syllabus responses.
- Cleaned syllabus extraction output to strip page headers, textbook/reference sections, and similar non-syllabus noise.
- Fixed stale `Milvus.py` function caching in `api/views.py` so backend code changes are picked up reliably.
- Added fast Milvus health checks, reduced slow cloud retry behavior, and added a circuit breaker for unhealthy Milvus periods.
- Removed the Groq `/models` pre-probe and now handle Groq availability by standard request exception flow.
- Stabilized Milvus Cloud collection rebuilds by waiting for drop/create visibility before reuse.
- Fixed markdown ordered-list numbering so adjacent ordered lists continue sequentially in the frontend.
- Fixed paragraph rendering so plain-text multi-paragraph responses keep visible paragraph breaks in chat.

## Operational Notes

- Full offline usage still requires the local backend and Ollama stack to be running.
- Online mode does not guarantee Milvus Cloud retrieval unless the configured Zilliz endpoint is healthy.
- Syllabus extraction is deterministic for syllabus/unit-style queries and is intended to return source text from the uploaded PDFs rather than generalized summaries.
- For current local development, restart the backend after changing `Milvus.py` so any long-running process drops stale in-memory state immediately.

## Enhancement Opportunities (Deep-Dive)

- Add server-side conversation persistence (user-owned threads in DB) to support multi-device continuity and avoid localStorage-only history.
- Add explicit latency breakdown metrics for retrieval, rerank, and generation phases (Prometheus histograms + trace IDs on each phase).
- Move expensive index sync/rebuild out of request path (background job queue + explicit indexing status endpoint).
- Introduce retrieval quality controls (citation spans, source confidence, and low-confidence fallback prompts).
- Consolidate legacy duplicate RAG modules (`optimized_rag.py`, `rag_service.py`, `api/optimized_rag.py`) to reduce drift and maintenance risk.

## Important Notes

- `main.py` launches the `Frontend/` workspace as the active UI.
- Keep secrets out of source control and rotate any previously committed credentials.
- Generated artifacts (`db.sqlite3`, local vector DB files, coverage/build outputs) should be treated as runtime outputs, not source of truth.

## Kept Project Documentation Files

Per repository cleanup, only these Markdown files are retained:

- `README.md`
- `Final_Integration Summary.md`
- `Architecture_Diagrams.md`
