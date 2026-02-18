# Skill: add-endpoint

## When To Use
- Adding a new backend API endpoint in Django (`api/`).

## Preconditions
- Contract is defined (method, auth requirement, request shape, response schema).
- Needed env vars already defined or planned.

## Step-by-Step Plan
1. Add route in `api/urls.py`.
2. Implement handler in `api/views.py` or `api/auth_views.py`.
3. Apply `@jwt_required` and `@ratelimit` as appropriate.
4. Return consistent JSON shape (`success`, `error`, optional `trace_id`).
5. Add tests in `api/tests.py` for success and failure paths.
6. Update frontend client in `Frontend/src/lib/api-client.ts` if exposed to UI.

## Edge Cases In This Repo
- Missing `djangorestframework-simplejwt` should return `503` in auth flows.
- Ensure request size/length rules align with `MAX_QUESTION_LENGTH` patterns.

## Validation Checklist
- `python manage.py test api.tests`
- `python manage.py check`
- Smoke call with curl includes expected status and payload.

## Rollback Strategy
- Remove route from `api/urls.py`.
- Revert handler and tests together.
- Verify no frontend callsites remain.

## Real Example
- Add `GET /api/model-info/` using `api/views.py` pattern and register in `api/urls.py`.
