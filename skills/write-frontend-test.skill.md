# Skill: write-frontend-test

## When To Use
- Frontend behavior changes in API client, store, routing, auth, or accessibility-critical UI.

## Preconditions
- Component/module has deterministic input/output behavior.

## Step-by-Step Plan
1. Select test layer:
   - `lib` logic -> `Frontend/src/lib/__tests__/`.
   - store behavior -> `Frontend/src/store/__tests__/`.
   - accessibility route/page -> `Frontend/src/pages/__tests__/`.
   - flow-level -> Playwright in `Frontend/tests/e2e/`.
2. Mock network where unit tests are sufficient.
3. Assert user-visible outcomes and error messaging.
4. For snapshots, update intentionally and commit baseline.

## Edge Cases In This Repo
- Env parsing in `config.ts` throws hard; tests must set env explicitly.
- Auth tokens are split across `localStorage` and `sessionStorage`.

## Validation Checklist
- `cd Frontend && npm run test`
- `cd Frontend && npm run test:coverage`
- `cd Frontend && npm run test:e2e` when UI flow is affected.

## Rollback Strategy
- Revert test and feature changes together.
- Keep baseline snapshots in sync with intended UI state.

## Real Example
- Add retry-path assertions to `Frontend/src/lib/__tests__/api-client.test.ts`.
