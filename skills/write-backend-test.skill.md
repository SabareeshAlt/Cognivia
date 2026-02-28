# Skill: write-backend-test

## When To Use
- Any backend behavior change in `api/`, `Milvus.py`, or settings-driven logic.

## Preconditions
- Behavior under test has a stable expected contract.
- External systems are mockable or not needed.

## Step-by-Step Plan
1. Choose test scope:
   - Endpoint contract -> `api/tests.py`.
   - Pure decision logic -> dedicated test module (e.g., `api/test_index_sync.py`).
2. Add negative-path assertions first (auth fail, invalid JSON, timeout/degraded status).
3. Add success-path assertions with exact keys and status codes.
4. Mock expensive integrations (`Milvus`, network calls) when unit-level.

## Edge Cases In This Repo
- Readiness is async-cached; tests should set cache state/mocks deterministically.
- Auth tests must handle optional SimpleJWT availability guard.

## Validation Checklist
- `python manage.py test`
- Confirm new tests fail before implementation and pass after.

## Rollback Strategy
- Remove newly added tests only with corresponding feature rollback.
- Keep invariant tests for unchanged contracts.

## Real Example
- Extend `HealthEndpointTests` in `api/tests.py` for new readiness field semantics.
