# AGENTS.md

## Repository Cognitive Model

### Architectural Overview
- Primary architecture: modular monolith.
- Backend: Django API service (`rag_project`, `api`) with JWT auth, rate limiting, structured logging, and RAG orchestration.
- Retrieval subsystem: Milvus-backed vector retrieval in `Milvus.py` with ingestion lifecycle + tracking state persisted in Django model `api.models.IndexedDocument`.
- Frontend: Vite + React + TypeScript SPA in `Frontend/` with route-level lazy loading, Zustand chat store, React Query, and typed API client.
- Runtime launcher: `main.py` starts backend + frontend together for local development, including migrations and process supervision.
- CI/CD: GitHub Actions split into `backend`, `frontend`, `rag-eval-gate`, and separate supply-chain security workflow.

### Domain Model Summary
- User/auth domain:
  - Registration/login/refresh/profile endpoints in `api/auth_views.py`.
  - JWT bearer enforcement via `api/auth_utils.py`.
- Conversation domain:
  - Chat sessions and messages stored in client-side Zustand (`Frontend/src/store/chat-store.ts`).
  - API request flow to `/api/ask/` and `/api/ask/stream/`.
- Retrieval/knowledge domain:
  - Source PDFs in `documents/`.
  - Chunking + embeddings + Milvus indexing in `Milvus.py`.
  - Index state tracking in `api.models.IndexedDocument` (content hash + chunk profile).
- Operations domain:
  - Health liveness/readiness split (`/api/health/live/`, `/api/health/ready/`).
  - Request tracing via `X-Request-ID` middleware and logging context.

### Key Invariants
- Environment-driven configuration is mandatory. `rag_project/settings.py` fails fast on missing/invalid env vars.
- Protected RAG endpoints must stay authenticated (`jwt_required`) and rate-limited.
- Request/response traceability must preserve `X-Request-ID` propagation and logging context.
- Retrieval behavior must remain deterministic for no-context paths (`INSUFFICIENT_CONTEXT_MESSAGE` in `Milvus.py`).
- Ingestion must be idempotent by file hash + chunk profile; avoid duplicate indexing from unchanged corpora.
- Frontend config must remain strict and typed (`Frontend/src/lib/config.ts` required env parsing).

### Core Abstractions
- `Milvus.py`:
  - Collection bootstrap and schema enforcement.
  - Rebuild decision (`compute_sync_decision`, `compute_rebuild_state`).
  - Vector store initialization + retriever caching.
  - Answer generation pipeline and streaming fallback.
- `api/views.py`:
  - API boundary for ask + stream + liveness/readiness.
  - Lazy load and async readiness probe cache for dependency checks.
- `api/auth_views.py` + `api/auth_utils.py`:
  - Token issuance, identity binding, endpoint guardrails.
- `Frontend/src/lib/api-client.ts`:
  - Timeout, retry, refresh-token retry path, API error taxonomy.
- `main.py`:
  - Local orchestration and failure handling for dual-stack startup.

### System Constraints
- Milvus cloud-only mode is expected (controlled by env flags and credentials).
- Ollama must be reachable for embeddings/LLM (`OLLAMA_BASE_URL`).
- Django test/CI config relies on env injection; changing required env keys impacts pipeline stability.
- Frontend depends on Vite env keys; missing keys hard-fail early.

### Critical Flows
- Auth flow:
  - `POST /api/auth/register/` -> JWT issue.
  - `POST /api/auth/login/` -> JWT issue.
  - `POST /api/auth/refresh/` -> access refresh.
  - `GET /api/auth/me/` -> profile.
- Ask flow:
  - Frontend typed client -> authenticated POST to `/api/ask/` or `/api/ask/stream/`.
  - Backend loads RAG modules lazily, retrieves context, returns deterministic fallback if no docs.
- Ingestion flow:
  - `create_milvus_collection.py` or runtime auto-sync -> schema ensure -> chunk/embed -> batch insert -> state tracking update.
- Readiness flow:
  - `/api/health/ready/` checks Ollama and asynchronously probes vector dependencies with cached state.

## Coding Laws for This Repository

### Strict Patterns That Must Not Be Violated
- Do not hardcode secrets, endpoints, or toggles in code. Use `.env` and required env loaders.
- Do not bypass auth/rate-limit on ask endpoints.
- Do not remove request trace ID handling in middleware/logging filters.
- Do not reintroduce parallel legacy retrieval logic outside `Milvus.py` as primary path.
- Do not change health endpoints back to blocking dependency calls.

### Naming Conventions
- Backend modules: snake_case filenames, Django conventions.
- API JSON keys: snake_case from backend (`trace_id`), camelCase in frontend domain objects where already established.
- Frontend TypeScript symbols: PascalCase for components, camelCase for functions/variables.
- Script names: verb-driven (`create_milvus_collection.py`, `setup_milvus.py`).

### File Placement Rules
- Django API handlers: `api/views.py` and auth-specific in `api/auth_views.py`.
- Retrieval/indexing internals: `Milvus.py`.
- DB schema for Django app state: `api/models.py` + `api/migrations/`.
- Frontend domain logic:
  - API client and config in `Frontend/src/lib/`.
  - State in `Frontend/src/store/`.
  - Routes/pages in `Frontend/src/pages/`.
- CI definitions only in `.github/workflows/`.

### Dependency Boundaries
- Backend view code may depend on Django + local modules; keep external integration details encapsulated in retrieval modules.
- Frontend components should consume typed interfaces from `Frontend/src/lib/*` and store modules, not raw `fetch` calls.
- Tests should mock integration boundaries rather than asserting on network behavior where unit tests suffice.

### Anti-Patterns Specific to This Repo
- Re-adding generic or duplicate vector store modules that diverge from `Milvus.py`.
- Silent ingestion with no progress logs or timeout bounds.
- Adding endpoint logic without trace ID propagation and structured error payload.
- Introducing env defaults that mask missing security-critical configuration.
- Growing frontend business logic inside page components instead of `lib/` and `store/`.

## Change Safety Protocol

### Before Modifying Code
- Confirm active path ownership:
  - Retrieval path: `api/views.py` + `Milvus.py`.
  - Auth path: `api/auth_views.py` + `api/auth_utils.py`.
  - Frontend transport: `Frontend/src/lib/api-client.ts`.
- Map env variables touched and verify both `.env.example` and CI env coverage.
- Check for compatibility impact on tests (`api/tests.py`, `api/test_index_sync.py`, frontend tests).

### Regression Risk Zones
- `Milvus.py`: ingestion control, schema lifecycle, retriever caching.
- `api/views.py`: async readiness cache and ask/stream behavior.
- `rag_project/settings.py`: required env validators (high blast radius).
- `Frontend/src/lib/config.ts` + `api-client.ts`: client boot failures and API call resilience.
- `.github/workflows/ci.yml`: required env drifts and flaky gate behavior.

### Required Validation Steps
- Backend:
  - `python manage.py check`
  - `python manage.py test`
- Frontend:
  - `cd Frontend && npm run lint`
  - `cd Frontend && npm run test`
  - `cd Frontend && npm run build`
  - `cd Frontend && npm run perf:budget`
- E2E when changing auth/chat UX:
  - `cd Frontend && npm run test:e2e`
- Retrieval changes:
  - run controlled bootstrap (`python create_milvus_collection.py --recreate-safe`) and probe `GET /api/health/ready/`.

### Testing Heuristics
- Prefer targeted tests first, then full suite.
- For backend endpoint behavior, assert status + JSON contract + deterministic error payload.
- For retrieval state transitions, unit-test decision logic (`compute_sync_decision`) and avoid long integration tests in unit layer.
- For frontend resiliency, test timeout/retry/auth-refresh paths in `Frontend/src/lib/__tests__/api-client.test.ts`.

### Build Validation Steps
- Ensure env additions are reflected in:
  - `.env.example`
  - `rag_project/settings.py` (backend)
  - `Frontend/.env.example` + `Frontend/src/lib/config.ts` (frontend)
  - `.github/workflows/ci.yml` as needed.

## Acceleration Playbooks

### Add a Feature Correctly
1. Place feature entry in the correct boundary (backend endpoint vs retrieval core vs frontend lib/store/page).
2. Define/extend contract types first (backend JSON schema + frontend TypeScript expectations).
3. Add minimal tests around behavior and failure modes.
4. Wire metrics/logging for observability (trace IDs, telemetry events).
5. Validate full stack with local runner (`python main.py`) and targeted curls.

### Refactor Safely
1. Identify canonical module first (avoid touching deprecated compatibility shims unless intentionally cleaning them).
2. Add/extend tests around current behavior before moving code.
3. Refactor in small slices with no contract drift.
4. Run backend + frontend + gate checks after each slice.
5. Remove dead paths only after proving no active references.

### Debug Efficiently
- Backend runtime issues:
  - start with `python main.py --backend-only`.
  - inspect readiness endpoints (`/api/health/live/`, `/api/health/ready/`).
  - follow request IDs in logs.
- Retrieval issues:
  - inspect collection state with `create_milvus_collection.py --recreate-safe`.
  - verify chunking and ingestion progress logs.
- Frontend issues:
  - verify env parse in `Frontend/src/lib/config.ts`.
  - inspect `ApiError` metadata (`status`, `traceId`).

### Add Tests Properly
- Backend endpoint tests in `api/tests.py`.
- Backend pure-logic tests in focused modules like `api/test_index_sync.py`.
- Frontend unit/a11y tests in `Frontend/src/**/__tests__/`.
- E2E tests in `Frontend/tests/e2e/` only for critical user journeys.

### Introduce a New Dependency
1. Justify why existing stack cannot satisfy the requirement.
2. Add to appropriate manifest (`requirements_django.txt` or `Frontend/package.json`).
3. Update CI workflows if tooling/runtime expectations change.
4. Add one integration proof path and one regression test.
5. Document operational implications (env vars, startup requirements, security).

### Optimize Performance
- Backend:
  - reduce cold start by warmup and retriever caching.
  - keep readiness non-blocking.
  - batch ingestion with bounded timeouts and progress logging.
- Frontend:
  - preserve route lazy loading.
  - monitor bundle budget gate.
  - keep network retries targeted for transient statuses only.

## Architectural Decision Heuristics
- Prefer explicit over implicit configuration.
- Prefer deterministic fallbacks over best-effort hallucination paths.
- Prefer idempotent, observable ingestion operations over opaque one-shot scripts.
- Prefer contract-first API changes with typed frontend coupling.
- Prefer adding capability in canonical modules instead of introducing parallel stacks.
- Prefer small reversible changes with clear rollback points.

## Repository Intelligence Mapping

### Tech Stack
- Python (Django, DRF, SimpleJWT, django-ratelimit, dotenv, requests, pypdf, langchain, langchain-ollama, langchain-milvus, pymilvus).
- TypeScript/React (Vite, React Router, React Query, Zustand, Radix UI, Tailwind, Vitest, Playwright, ESLint).
- Runtime dependencies: Ollama, Milvus/Zilliz Cloud.

### Architectural Pattern
- Modular monolith with clear backend/frontend boundary and retrieval subsystem specialization.

### Internal Dependency Graph (High-Level)
- `rag_project.settings` -> all backend runtime behavior/env constraints.
- `api/urls.py` -> `api/views.py` + `api/auth_views.py`.
- `api/views.py` -> lazy import `Milvus.py` functions.
- `Milvus.py` -> chunking, embeddings, Milvus client, Django tracking model.
- Frontend pages -> `lib/api-client.ts`, `lib/config.ts`, `store/chat-store.ts`.

### Build and Tooling
- Backend: pip + Django manage commands.
- Frontend: npm/Vite/Vitest/Playwright.
- Orchestration: root `main.py`.

### Test Strategy
- Backend unit/integration-ish endpoint tests in Django test suite.
- Retrieval decision tests in dedicated module.
- Frontend unit/a11y tests via Vitest + jest-axe.
- E2E smoke path with Playwright visual baseline.
- Regression quality gate for RAG outputs (`eval/rag_eval.py`).

### Code Conventions and Repeated Idioms
- Backend: fail-fast env getters, JSON error payloads with `success` flags, trace IDs.
- Frontend: strict env parsing, typed API errors, resilience wrappers (timeout + retry), local storage/session storage split.

### Performance-Sensitive Areas
- Milvus ingestion pipeline (chunking, embedding, insert batching).
- First retrieval call and readiness probes.
- Frontend ChatPage rendering + streaming updates.

### Security-Sensitive Areas
- JWT issuance/validation and refresh handling.
- Rate limit policies and 429 responses.
- Secret-bearing env vars (Milvus token, Django secret).
- CSP/headers in frontend static assets.

### Configuration Patterns
- Backend: required env with strict type validation in settings.
- Frontend: required Vite env with runtime parse/validation.
- CI: env mirrored explicitly per job.

### Deployment Strategy (Inferable)
- Intended for container/server deployment with Gunicorn support (`requirements_django.txt`), though repo currently optimized for local/dev orchestration.

### CI/CD Structure
- `.github/workflows/ci.yml`:
  - backend tests
  - frontend lint/test/build/perf/e2e
  - RAG eval gate
- `.github/workflows/security-supply-chain.yml`:
  - pip audit + SBOM
  - npm audit + SBOM

### Linting and Formatting
- Frontend ESLint with TS and react-hooks rules.
- No centralized Python formatter config committed; maintain consistency with existing style.

### Error Handling Philosophy
- Explicit user-facing JSON errors backend-side.
- Typed `ApiError` frontend-side with structured status/code/traceId.
- deterministic fallback for insufficient retrieval context.

### Logging Patterns
- Structured formatter with request context filters.
- Milvus pipeline logs include stage/progress and warnings.
- Frontend telemetry captures UI errors, rejections, web vitals.

### State Management Approach
- Frontend: Zustand persisted chat sessions + session-scoped tokens.
- Backend: stateless JWT for auth, DB-backed index metadata state.

### Data Layer Structure
- Django DB for users and ingestion metadata.
- Milvus vector collection for chunk embeddings.
- Local docs folder as source corpus.

### API Design Style
- JSON REST endpoints with explicit auth and trace IDs.
- Streaming via `text/event-stream` route.
- Health split into liveness/readiness.

### Domain Boundaries
- Authentication boundary: `api/auth_*`.
- Retrieval boundary: `Milvus.py`.
- API orchestration boundary: `api/views.py`.
- Frontend domain boundary: `Frontend/src/lib`, `Frontend/src/store`, `Frontend/src/pages`.

## How the Agent Should Continue Learning This Repository

### Updating Mental Models
- On every new top-level module, classify it into existing boundaries or mark as boundary expansion.
- Rebuild dependency map when `api/urls.py`, `Milvus.py`, `rag_project/settings.py`, or `Frontend/src/lib/config.ts` change.

### Detecting Architectural Drift
- Flag duplicate retrieval logic outside canonical module.
- Flag endpoint additions without auth/rate-limit/trace patterns.
- Flag env additions not mirrored in `.env.example` and CI env blocks.
- Flag frontend network calls outside `api-client.ts`.

### Refining Sub-Agents Over Time
- After each major feature, update corresponding `/agents/*.md` with new decision boundaries and examples.
- Promote repeated multi-step tasks into `/skills/*.skill.md` with concrete validation/rollback.

### Adding New Skills Safely
1. Confirm task recurs at least twice.
2. Define strict preconditions and termination criteria.
3. Include concrete file-path examples from this repo.
4. Include validation and rollback checklists.
5. Add one anti-pattern section to prevent misuse.
