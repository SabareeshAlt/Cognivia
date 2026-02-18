# Skill: add-frontend-route

## When To Use
- Introducing a new page/route in the React SPA.

## Preconditions
- Route auth requirement and navigation entry points are defined.

## Step-by-Step Plan
1. Add page component under `Frontend/src/pages/`.
2. Add lazy import and route in `Frontend/src/App.tsx`.
3. Wrap with `ProtectedRoute` if auth-gated.
4. Connect API/data through `lib/api-client.ts` and state through `store/` when needed.
5. Add route tests and, if critical flow, Playwright coverage.

## Edge Cases In This Repo
- Keep suspense fallback behavior intact.
- Preserve not-found redirect behavior (`/404`).

## Validation Checklist
- `cd Frontend && npm run test`
- `cd Frontend && npm run build`
- Manual navigation smoke test with and without auth state.

## Rollback Strategy
- Remove route + page + nav links together.
- Verify router has no dangling imports.

## Real Example
- Add `/settings` page with protected route and telemetry instrumentation.
