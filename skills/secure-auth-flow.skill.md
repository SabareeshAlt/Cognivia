# Skill: secure-auth-flow

## When To Use
- Modifying registration/login/refresh/me endpoints or token handling.

## Preconditions
- Threat model considered (credential stuffing, token theft, replay, abuse).

## Step-by-Step Plan
1. Keep endpoint decorators and rate limits in `api/auth_views.py`.
2. Preserve `jwt_required` checks in protected endpoints.
3. Ensure errors do not leak sensitive internals.
4. Validate frontend storage behavior (`localStorage` user + `sessionStorage` tokens).
5. Add tests for unauthorized, invalid token, missing token cases.

## Edge Cases In This Repo
- SimpleJWT optional dependency path should return service-unavailable where expected.
- Frontend refresh logic retries stream calls after 401.

## Validation Checklist
- `python manage.py test api.tests.AuthApiTests`
- `Frontend/src/lib/__tests__/api-client.test.ts` pass for refresh paths.

## Rollback Strategy
- Revert auth change and restore previous decorator/rate-limit configuration.
- Rotate keys/tokens if sensitive behavior was exposed.

## Real Example
- Adjust refresh token behavior while preserving `apiClient.askStream` 401 retry contract.
