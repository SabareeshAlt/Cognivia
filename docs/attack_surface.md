# Attack Surface

## External Endpoints

- `/api/auth/register/`
- `/api/auth/login/`
- `/api/auth/refresh/`
- `/api/auth/me/`
- `/api/ask/`
- `/api/ask/stream/`
- `/api/health/*`
- `/api/metrics/`
- `/api/admin/retrieval/diagnostics/`

## High-Risk Paths

- Auth refresh path (token lifecycle)
- Streaming ask endpoint (long-lived connections)
- Ingestion pipeline (resource-heavy operations)
- Milvus and Ollama dependency calls

## Defensive Controls

- JWT auth for protected endpoints
- Per-IP rate limiting
- Trace IDs for all requests
- Structured error payloads with trace correlation
- Security and dependency scanning in CI

