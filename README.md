# AcademeRAG-Final

## Project Summary
AcademeRAG-Final is a full-stack Retrieval-Augmented Generation system with:

- A Django backend API for authentication, chat, health, and diagnostics
- A React/Vite frontend for auth and chat UX
- A Milvus (Zilliz Cloud) vector retrieval pipeline for document-grounded responses
- Ollama-based embedding and generation integration
- CI and security workflows enforcing quality and supply-chain controls

This README documents the implemented system behavior and workflow, not sample usage.

## Implemented Architecture

### Backend Application Layer
- Django project configuration: `rag_project/settings.py`, `rag_project/urls.py`
- API module: `api/`
  - `auth_views.py`: register/login/refresh/me JWT flow
  - `auth_utils.py`: JWT verification helpers
  - `views.py`: ask endpoints (sync + streaming), health endpoints, metrics, admin diagnostics
  - `middleware.py`: request-id and metrics middleware
  - `rate_limit.py`: IP-based rate limiting hooks
  - `logging_*`: structured request-safe logging format and filters

### Retrieval Layer
- Canonical retrieval implementation: `Milvus.py`
  - Cloud credential validation
  - Embedding model wiring
  - Vector store initialization and readiness tracking
  - Streaming and non-streaming response paths
  - Retrieval diagnostics and fallback behavior
- Ingestion bootstrap: `create_milvus_collection.py`

### Frontend Layer
- Frontend app root: `Frontend/`
- Core implementation:
  - `src/pages/AuthPage.tsx`, `src/pages/ChatPage.tsx`
  - `src/lib/api-client.ts`, `src/lib/auth.ts`, `src/lib/config.ts`, `src/lib/feature-flags.ts`
  - `src/store/chat-store.ts`
- E2E and unit tests:
  - `tests/e2e/auth.spec.ts`
  - `src/**/__tests__/*`

## Data and Storage Model

AcademeRAG uses two storage systems with different responsibilities:

- Milvus/Zilliz Cloud (vector database):
  - Stores document embeddings and vector index
  - Used by retrieval pipeline in `Milvus.py`
- Django relational database (`DB_ENGINE=sqlite|postgres`):
  - Stores application state (users/auth and Django models)
  - Configured in `rag_project/settings.py`

This split is intentional: vector retrieval and app relational persistence are separate concerns.

## Implemented Runtime Workflow

### 1) Startup and Configuration
- Environment is loaded from `.env` and validated with fail-fast checks in `rag_project/settings.py`.
- Missing required keys raise startup errors immediately.
- `main.py` orchestrates backend + frontend startup, migration execution, health wait, and port conflict resolution.

### 2) Document Ingestion Workflow
- Source PDFs are read from `documents/`.
- `create_milvus_collection.py --recreate-safe` performs controlled ingestion:
  - Reuses existing collection when corpus/chunk profile matches
  - Rebuilds when source profile changes or state is absent
- Milvus cloud mode requires valid non-placeholder token and `https://` URI.

### 3) Query Workflow
- Authenticated client submits question to `/api/ask/` or `/api/ask/stream/`.
- Backend request pipeline:
  - JWT auth check
  - Rate-limit enforcement
  - Retrieval pipeline invocation through `Milvus.py`
  - Structured response with trace context
- Health workflow:
  - Liveness: process is up
  - Readiness: dependency-aware status (Django/Ollama/vector readiness cache)

## Security Implementation

Implemented controls include:

- JWT-based auth endpoints with token rotation path
- Per-endpoint rate limiting for auth and chat paths
- Strict environment-driven secrets/config (no hardcoded runtime secrets)
- CORS/CSRF controls driven by explicit origin lists
- Structured request logging with request IDs
- CI secret scanning and dependency auditing pipeline

## CI/CD Implementation

### CI Workflow (`.github/workflows/ci.yml`)
Implemented gates:

- Backend:
  - `python manage.py check`
  - `coverage run manage.py test`
  - `coverage report --fail-under=70`
- Frontend:
  - `npm run lint`
  - `npm run test`
  - `npm run test:coverage`
  - coverage threshold check from `coverage-summary.json`
  - `npm run build`
  - `npm run perf:budget` (uses `VITE_MAX_JS_BUNDLE_KB`)
  - `npm run test:e2e`
- Eval gate:
  - `python eval/rag_eval.py --mode mock --output eval/latest_report.json`

### Security Workflow (`.github/workflows/security-supply-chain.yml`)
Implemented gates:

- Gitleaks secret scan
- Backend: `pip-audit`, `bandit`, CycloneDX SBOM generation
- Frontend: `npm audit --audit-level=high`, CycloneDX SBOM generation

## Key Project Files

- Backend settings and routing:
  - `rag_project/settings.py`
  - `rag_project/urls.py`
- API implementation:
  - `api/views.py`
  - `api/auth_views.py`
  - `api/auth_utils.py`
  - `api/middleware.py`
- Retrieval implementation:
  - `Milvus.py`
  - `create_milvus_collection.py`
- Full-stack launcher:
  - `main.py`
- Frontend implementation:
  - `Frontend/src/pages/AuthPage.tsx`
  - `Frontend/src/pages/ChatPage.tsx`
  - `Frontend/src/lib/api-client.ts`
  - `Frontend/src/store/chat-store.ts`
- CI and security pipelines:
  - `.github/workflows/ci.yml`
  - `.github/workflows/security-supply-chain.yml`

## Operational Notes

- `.env` and `Frontend/.env` are intentionally git-ignored.
- `Frontend/tests/e2e/auth.spec.ts` is deterministic and does not depend on missing baseline snapshots in CI.
- Bundle budget threshold is controlled via `VITE_MAX_JS_BUNDLE_KB` (CI uses `600`).

