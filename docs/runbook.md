# Operations Runbook

## Startup

1. Validate env: `.env` values present and non-placeholder.
2. Run migrations: `python manage.py migrate`.
3. Ensure Ollama is reachable.
4. Ensure Milvus credentials are valid.
5. Start app: `python main.py` (dev) or containers (prod).

## Health Triage

- Liveness: `/api/health/live/`
- Readiness: `/api/health/ready/`
- Metrics: `/api/metrics/`

## Common Incidents

- Chat timeout: check Ollama and request latency metrics.
- Empty retrieval: inspect `/api/admin/retrieval/diagnostics/` and ingestion state.
- Auth failures: verify JWT refresh and blacklist behavior.

## Recovery

- Re-run safe ingest: `python create_milvus_collection.py --recreate-safe`
- If index corruption suspected, run force rebuild during maintenance window.
