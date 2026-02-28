# Agent Routing Matrix

Use this matrix to pick the fastest correct execution path for common request shapes.

## How To Use
1. Match request intent to closest row.
2. Start with `Primary Agent`.
3. If cross-cutting concerns appear, invoke `Secondary Agent`.
4. Execute the listed skill playbook.

| Request Type | Primary Agent | Secondary Agent | Default Skill(s) |
|---|---|---|---|
| Add/modify backend endpoint | `api-agent.md` | `security-agent.md` | `skills/add-endpoint.skill.md`, `skills/write-backend-test.skill.md` |
| Add auth behavior (login/register/refresh/me) | `security-agent.md` | `api-agent.md` | `skills/secure-auth-flow.skill.md`, `skills/write-backend-test.skill.md` |
| Refactor retrieval/indexing internals | `backend-agent.md` | `data-agent.md` | `skills/refactor-module.skill.md`, `skills/optimize-rag-ingestion.skill.md` |
| Create/recreate Milvus collection and ingest docs | `data-agent.md` | `performance-agent.md` | `skills/optimize-rag-ingestion.skill.md`, `skills/debug-runtime-error.skill.md` |
| Change Django model/schema | `data-agent.md` | `backend-agent.md` | `skills/add-migration.skill.md`, `skills/write-backend-test.skill.md` |
| Improve startup/readiness behavior | `backend-agent.md` | `performance-agent.md` | `skills/refactor-module.skill.md`, `skills/debug-runtime-error.skill.md` |
| Add frontend page/route | `frontend-agent.md` | `feature-agent.md` | `skills/add-frontend-route.skill.md`, `skills/write-frontend-test.skill.md` |
| Modify frontend API behavior/retries/errors | `frontend-agent.md` | `api-agent.md` | `skills/write-frontend-test.skill.md`, `skills/add-endpoint.skill.md` |
| Add feature flag (backend/frontend) | `feature-agent.md` | `devops-agent.md` | `skills/implement-feature-flag.skill.md`, `skills/update-ci-pipeline.skill.md` |
| Add/adjust structured logs | `backend-agent.md` | `build-agent.md` | `skills/add-structured-logging.skill.md` |
| Fix failing CI pipeline | `devops-agent.md` | `build-agent.md` | `skills/update-ci-pipeline.skill.md`, `skills/debug-runtime-error.skill.md` |
| Add dependency (pip/npm) | `build-agent.md` | `security-agent.md` | `skills/update-ci-pipeline.skill.md`, `skills/debug-runtime-error.skill.md` |
| Performance optimization (API, ingestion, bundle) | `performance-agent.md` | `architecture-agent.md` | `skills/optimize-rag-ingestion.skill.md`, `skills/refactor-module.skill.md` |
| Security hardening / abuse controls | `security-agent.md` | `architecture-agent.md` | `skills/secure-auth-flow.skill.md`, `skills/add-endpoint.skill.md` |
| Large cross-cutting redesign | `architecture-agent.md` | `refactor-agent.md` | `skills/refactor-module.skill.md`, then domain-specific skill |

## Fast Decision Rules
- If request touches `Milvus.py`, always include `data-agent.md` or `backend-agent.md`.
- If request touches `.github/workflows/`, always include `devops-agent.md`.
- If request introduces env vars, always include:
  - backend: `rag_project/settings.py` + `.env.example`
  - frontend: `Frontend/src/lib/config.ts` + `Frontend/.env.example`
  - CI parity check: `.github/workflows/ci.yml`
- If request touches `/api/ask` or `/api/ask/stream`, include `security-agent.md` for auth/rate-limit regression checks.

## Canonical File Ownership Reminders
- Retrieval canonical implementation: `Milvus.py`.
- API contract boundary: `api/views.py`, `api/auth_views.py`, `api/urls.py`.
- Frontend network contract: `Frontend/src/lib/api-client.ts`.
- Frontend route boundary: `Frontend/src/App.tsx`.
- Ingestion bootstrap scripts: `create_milvus_collection.py`, `setup_milvus.py`.
