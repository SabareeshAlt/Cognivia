# Skill: optimize-rag-ingestion

## When To Use
- Milvus ingestion appears slow, opaque, or unstable.

## Preconditions
- Milvus and Ollama connectivity validated.
- Collection-level strategy (reuse vs recreate) decided.

## Step-by-Step Plan
1. Confirm corpus and tracking state (`compute_rebuild_state` in `Milvus.py`).
2. Tune env knobs:
   - `ACADEMERAG_INGEST_BATCH_SIZE`
   - `ACADEMERAG_INGEST_MAX_SECONDS`
   - `ACADEMERAG_MILVUS_TIMEOUT_SECONDS`
3. Run `python create_milvus_collection.py --recreate-safe`.
4. Monitor stage logs:
   - parse/chunk progress
   - ingestion batch progress with ETA
5. Probe retrieval after ingest.

## Edge Cases In This Repo
- Duplicate root/documents PDF names can cause duplicate ingestion if dedupe logic regresses.
- AsyncMilvus warning is non-fatal in sync mode; do not treat as fatal unless inserts fail.

## Validation Checklist
- Ingestion completes without timeout.
- `GET /api/health/ready/` shows vector store ready.
- Sample retrieval returns non-empty results.

## Rollback Strategy
- Revert batch/timeout env tuning.
- Use `--recreate` only if state corruption suspected.

## Real Example
- Reduce batch size in `.env` and rerun safe recreate for more frequent progress and lower latency spikes.
