# Skill: add-structured-logging

## When To Use
- Need better observability for backend operations or long-running ingestion.

## Preconditions
- Log message purpose and audience are clear.
- Sensitive data redaction considered.

## Step-by-Step Plan
1. Use module logger (`logging.getLogger(__name__)`).
2. Include operation stage and measurable counters/durations.
3. Preserve request context via existing logging filters for API paths.
4. Avoid high-volume logs in tight loops unless throttled (e.g., every N pages/batches).
5. Add matching warning/error logs with actionable context.

## Edge Cases In This Repo
- Request IDs are injected through middleware; ingestion scripts may not have request context.
- Overly verbose logs during ingestion can overwhelm terminal and obscure failures.

## Validation Checklist
- Logs appear in local run and CI where relevant.
- No secrets/tokens emitted.

## Rollback Strategy
- Remove non-essential logs first.
- Keep critical error logs and progress markers.

## Real Example
- Batch/ETA progress logs in `Milvus.py` ingestion loop.
