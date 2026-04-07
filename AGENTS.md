# Repository Guidelines

## Project Structure & Module Organization
This repository is a full-stack academic RAG app with Django + React.

- `rag_project/` and `api/`: Django project config, auth, RAG endpoints, health/metrics, middleware.
- `Milvus.py`, `create_milvus_collection.py`, `setup_milvus.py`: retrieval/indexing pipeline.
- `Frontend/`: primary React + TypeScript + Vite client used by `main.py` and CI.
- `documents/`: PDF corpus used for ingestion/testing.
- `eval/`: RAG quality gates (`rag_eval.py`, golden set, thresholds).
- `.github/workflows/`: CI and security pipelines.

Note: root-level `src/` exists, but active frontend work should target `Frontend/src/` unless a task explicitly requires the root Vite app.

## Build, Test, and Development Commands
- `python main.py`: run backend + frontend together (default local workflow).
- `python manage.py runserver 127.0.0.1:8000`: run Django API only.
- `cd Frontend && npm run dev`: run frontend only.
- `python manage.py check && python manage.py test`: backend validation and tests.
- `cd Frontend && npm run lint && npm run test && npm run build`: frontend lint/test/build.
- `cd Frontend && npm run test:coverage && npm run test:e2e`: coverage and Playwright E2E.
- `python create_milvus_collection.py --recreate-safe`: rebuild vector collection safely.

## Coding Style & Naming Conventions
- Python: follow PEP 8, 4-space indentation, `snake_case` for functions/modules, `PascalCase` for classes.
- TypeScript/React: 2-space indentation, `PascalCase` components, `camelCase` hooks/utilities, tests colocated in `__tests__` or `*.test.ts(x)`.
- Run ESLint before PRs: `cd Frontend && npm run lint`.
- Keep environment-driven config in `.env`; do not hardcode secrets.

## Testing Guidelines
- Backend tests run with Django’s test runner (`manage.py test`) and should cover API behavior, auth flows, and retrieval fallbacks.
- Frontend unit/integration tests use Vitest + Testing Library; E2E uses Playwright.
- Add/adjust tests with feature changes; for retrieval changes, update `eval/golden_set.json` inputs if expected behavior shifts.

## Commit & Pull Request Guidelines
- Use short Conventional Commit-style subjects seen in history: `docs:`, `chore:`, `ci:`, `merge:`.
- Keep commits focused by concern (backend, frontend, infra, docs).
- PRs should include: purpose, affected modules, test evidence (commands run), and UI screenshots for `Frontend/` changes.
- Link related issues/tasks and call out any env/config changes explicitly.

## Security & Configuration Tips
- Never commit secrets, `.env`, or generated artifacts (`db.sqlite3`, local vector DB/cache files, coverage/build outputs).
- Validate Groq/Milvus/Ollama settings locally before pushing; broken provider config can pass lint but fail runtime readiness.
