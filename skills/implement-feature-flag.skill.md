# Skill: implement-feature-flag

## When To Use
- Introducing controllable behavior toggles in frontend or backend.

## Preconditions
- Flag ownership and default behavior are defined.
- Rollout plan and emergency disable path are defined.

## Step-by-Step Plan
1. Add env key to `.env.example` (and `.env` for local).
2. Backend flags:
   - parse in `rag_project/settings.py` using strict env loaders.
3. Frontend flags:
   - parse in `Frontend/src/lib/config.ts`.
   - resolve in `Frontend/src/lib/feature-flags.ts`.
4. Wire behavior at callsite with explicit fallback path.
5. Add tests for enabled/disabled states.
6. Mirror env key in `.github/workflows/ci.yml` if required by runtime.

## Edge Cases In This Repo
- Frontend missing flag env crashes app startup.
- Default values must avoid disabling critical auth or chat paths unexpectedly.

## Validation Checklist
- Both flag states tested.
- CI env parity confirmed.

## Rollback Strategy
- Remove flag branch and parser entries atomically.
- Keep feature default behavior explicit.

## Real Example
- Extend diagnostics feature toggle via `VITE_FEATURE_DIAGNOSTICS_PANEL` path.
