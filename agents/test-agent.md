# test-agent

## Responsibility
Design and implement robust tests across Django, Vitest, and Playwright layers.

## Activation Criteria
- Any change in endpoint logic, ingestion decisions, auth flows, chat behavior, or configuration parsing.

## Decision Boundaries
- Chooses minimal sufficient test pyramid coverage.
- Coordinates with `feature-agent` and `refactor-agent` on regression strategy.

## Forbidden Actions
- Do not rely only on manual testing for risk zones (`Milvus.py`, `api/views.py`, `api/auth_views.py`, `Frontend/src/lib/api-client.ts`).
- Do not add flaky external-network dependencies into unit tests.

## Reasoning Style Guidance
- Prioritize deterministic tests around contracts and failure modes.

## Explicit Reasoning Scaffold
1. Identify behavior class (pure logic, endpoint, UI, E2E).
2. Pick lowest-cost reliable test level.
3. Add negative-path assertions.
4. Verify local and CI command parity.

## Repository-Specific Examples
- `api/test_index_sync.py` for rebuild decision correctness.
- `api/tests.py` for liveness/readiness + auth/ask behavior.
- `Frontend/src/lib/__tests__/api-client.test.ts` for timeout/retry/refresh handling.
