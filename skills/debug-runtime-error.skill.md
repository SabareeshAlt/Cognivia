# Skill: debug-runtime-error

## When To Use
- Any runtime failure in startup, API responses, ingestion, auth, or frontend requests.

## Preconditions
- Reproduction command and error context available.

## Step-by-Step Plan
1. Reproduce with minimal command (`python main.py --backend-only` or targeted script).
2. Capture logs with request IDs and exact stack traces.
3. Classify boundary:
   - config/env
   - network/dependency
   - contract mismatch
   - code regression
4. Apply smallest fix and re-run reproduction.
5. Add regression test when applicable.

## Edge Cases In This Repo
- Missing env keys fail at settings load time.
- Readiness can be degraded initially while async probe warms up.
- Frontend config parser throws if Vite env missing.

## Validation Checklist
- Original failure no longer reproduces.
- Relevant test suite passes.
- No new warnings/errors in startup logs.

## Rollback Strategy
- Revert last patch and restore known-good branch state.
- Keep diagnostic notes for follow-up.

## Real Example
- Diagnose Milvus `UNAUTHENTICATED` by validating URI/region/token in `.env` then re-probing `health/ready`.
