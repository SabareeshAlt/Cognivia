# AcademeRAG-Final

AcademeRAG-Final is a full-stack Retrieval-Augmented Generation (RAG) platform for academic question answering. It combines a Django API backend, a React/Vite frontend, and a Milvus-based retrieval layer with provider-routed LLM generation (Groq cloud and local Ollama fallback).

## What This Project Does

- Authenticates users with JWT access/refresh tokens.
- Accepts user questions through REST and streaming endpoints.
- Retrieves relevant document chunks from Milvus/Zilliz before generation.
- Generates grounded responses with Groq-first routing and optional local Ollama fallback.
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
5. Retrieval fetches relevant chunks from vector store.
6. Generation composes final answer and returns JSON or stream chunks.

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

## LLM Routing

- `ACADEMERAG_LLM_PROVIDER=groq` routes generation to Groq first.
- If Groq is enabled and unavailable, fallback to Ollama occurs only when Ollama is reachable.
- `GROQ_BASE_URL` must be the API endpoint (`https://api.groq.com/openai/v1`), not the Groq Console URL.

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
