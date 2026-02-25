# AcademeRAG

Production-minded Retrieval-Augmented Generation (RAG) application with a Django API, React frontend, and Milvus (Zilliz Cloud) retrieval backend.

## What This Repository Implements

- Secure JWT auth flow: register, login, refresh, profile
- Protected and rate-limited RAG endpoints
- Milvus-based ingestion and retrieval pipeline in `Milvus.py`
- Deterministic no-context fallback behavior
- Readiness/liveness health probes
- Full-stack local runner (`main.py`) with migration + process supervision
- Frontend SPA (React + TypeScript + Vite) with typed API client, retry/timeout handling, and state management
- CI workflows for backend/frontend validation and security supply-chain checks

## High-Level Architecture

- Backend: Django + DRF-style JSON API in `rag_project/` and `api/`
- Retrieval: canonical implementation in `Milvus.py`
- Vector DB: Milvus/Zilliz Cloud
- LLM + embeddings: Ollama
- Frontend: Vite + React + TypeScript in `Frontend/`
- Local orchestration: `main.py` runs backend + frontend together

## Repository Layout

```text
.
├── api/
│   ├── auth_views.py            # JWT auth endpoints
│   ├── auth_utils.py            # JWT guard helpers
│   ├── views.py                 # ask + health endpoints
│   ├── models.py                # IndexedDocument tracking model
│   └── urls.py                  # API route map
├── rag_project/
│   ├── settings.py              # fail-fast env config
│   └── urls.py                  # root URL configuration
├── Frontend/
│   ├── src/lib/                 # config, api client, typed contracts
│   ├── src/store/               # Zustand chat/auth state
│   ├── src/pages/               # route-level pages
│   └── package.json             # frontend scripts
├── documents/                   # source PDFs for ingestion
├── Milvus.py                    # canonical retrieval + ingestion lifecycle
├── create_milvus_collection.py  # controlled ingestion/bootstrap entrypoint
├── main.py                      # unified local launcher
├── manage.py                    # Django CLI entrypoint
├── requirements_django.txt      # backend dependencies
└── .github/workflows/           # CI/CD pipelines
```

## Prerequisites

- Python 3.9+
- Node.js 18+
- npm
- Ollama running locally
- Zilliz/Milvus cloud endpoint + token (for cloud mode)

## 1) Setup

### Backend setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_django.txt
```

### Frontend setup

```bash
cd Frontend
npm install
cd ..
```

### Environment files

```bash
cp .env.example .env
cp Frontend/.env.example Frontend/.env
```

Then set required values in `.env`, especially:

- `DJANGO_SECRET_KEY`
- `ACADEMERAG_ENABLE_MILVUS_CLOUD=true`
- `ACADEMERAG_MILVUS_URI`
- `ACADEMERAG_MILVUS_TOKEN`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL_NAME`
- `EMBEDDING_MODEL`

## 2) Database Migration

```bash
./.venv/bin/python manage.py migrate
```

## 3) Ingest Documents into Milvus

Place PDFs in `documents/`.

Recommended ingestion command:

```bash
./.venv/bin/python create_milvus_collection.py --recreate-safe
```

What `--recreate-safe` does:

- Reuses collection if corpus/chunk profile is unchanged
- Rebuilds collection only when changes are detected or tracking state is missing

Other ingestion modes:

```bash
# Force drop + full rebuild
./.venv/bin/python create_milvus_collection.py --recreate

# Ensure schema only, skip document ingestion
./.venv/bin/python create_milvus_collection.py --schema-only
```

## 4) Run the Application

Recommended (backend + frontend together):

```bash
./.venv/bin/python main.py
```

Useful runner options:

```bash
# backend only
./.venv/bin/python main.py --backend-only

# frontend only
./.venv/bin/python main.py --frontend-only

# skip migrations on startup
./.venv/bin/python main.py --skip-migrate
```

### Startup behavior notes

- `main.py` now auto-resolves local port conflicts by selecting the next available port.
- It prints final readiness URLs for backend and frontend after startup.

## API Endpoints

Base API prefix: `/api/`

### Auth

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/refresh/`
- `GET /api/auth/me/` (requires `Authorization: Bearer <access_token>`)

### Chat / RAG

- `POST /api/ask/` (JWT required, rate-limited)
- `POST /api/ask/stream/` (JWT required, SSE)

Request body:

```json
{
  "question": "Explain gradient descent"
}
```

Optional stream flag on `/api/ask/`:

```json
{
  "question": "Explain gradient descent",
  "stream": true
}
```

### Health

- `GET /api/health/` (readiness alias)
- `GET /api/health_check/` (readiness alias)
- `GET /api/health/live/` (liveness)
- `GET /api/health/ready/` (dependency-aware readiness)
- `GET /api/metrics/` (Prometheus-style metrics)
- `GET /api/admin/retrieval/diagnostics/` (admin-only retrieval diagnostics)

## Quick API Test Commands

### Register

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123","name":"User"}'
```

### Login

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'
```

### Ask (replace `$TOKEN`)

```bash
curl -s -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize the indexed documents"}'
```

### Ready check

```bash
curl -s http://127.0.0.1:8000/api/health/ready/
```

## Testing and Validation

Backend:

```bash
./.venv/bin/python manage.py check
./.venv/bin/python manage.py test
```

Frontend:

```bash
cd Frontend
npm run lint
npm run test
npm run build
npm run perf:budget
```

E2E (for auth/chat UX changes):

```bash
cd Frontend
npm run test:e2e
```

RAG eval gate:

```bash
./.venv/bin/python eval/rag_eval.py --mode mock --output eval/latest_report.json
```

## Command Cheat Sheet

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_django.txt
cd Frontend && npm install && cd ..

# Env templates
cp .env.example .env
cp Frontend/.env.example Frontend/.env

# DB + ingest
./.venv/bin/python manage.py migrate
./.venv/bin/python create_milvus_collection.py --recreate-safe

# Run
./.venv/bin/python main.py

# Health
curl -s http://127.0.0.1:8000/api/health/live/
curl -s http://127.0.0.1:8000/api/health/ready/

# Backend tests
./.venv/bin/python manage.py check
./.venv/bin/python manage.py test

# Frontend checks
cd Frontend && npm run lint && npm run test && npm run build && npm run perf:budget
```

## Troubleshooting

### Milvus connection failure

- Verify cloud mode is enabled: `ACADEMERAG_ENABLE_MILVUS_CLOUD=true`
- Verify `ACADEMERAG_MILVUS_URI` and `ACADEMERAG_MILVUS_TOKEN`
- Re-run ingestion:

```bash
./.venv/bin/python create_milvus_collection.py --recreate-safe
```

### Ollama not reachable

```bash
ollama serve
ollama pull llama3.2
ollama pull mxbai-embed-large
```

### Readiness degraded

- Check `GET /api/health/ready/` response fields (`ollama`, `vector_store`, `milvus_cloud`)
- Inspect backend logs for request IDs and dependency errors

### Port conflict on startup

- `main.py` automatically selects nearby free ports and prints the resolved URLs
- If binding is blocked by OS permissions, run in a normal local shell session with network/socket access

## Implementation Rules and Invariants

- Canonical retrieval path is `api/views.py` -> `Milvus.py`
- Ask endpoints must remain authenticated and rate-limited
- Traceability requires `X-Request-ID` propagation and structured logging
- Env configuration remains strict and fail-fast in `rag_project/settings.py`
- Ingestion must remain idempotent by content hash + chunk profile tracking

## CI/CD

Workflows in `.github/workflows/` include:

- Backend checks and tests
- Frontend lint/test/build/perf/e2e checks
- RAG eval quality gate
- Security and supply-chain scanning
