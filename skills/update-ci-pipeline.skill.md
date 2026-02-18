# Skill: update-ci-pipeline

## When To Use
- New required env vars, new checks, or changed build/test commands.

## Preconditions
- Local commands are stable and documented.

## Step-by-Step Plan
1. Update `.github/workflows/ci.yml` job env and commands.
2. Update `.github/workflows/security-supply-chain.yml` if dependency/security tooling changed.
3. Ensure working-directory paths are correct.
4. Keep artifacts for diagnostics (coverage, eval reports, SBOMs).

## Edge Cases In This Repo
- Backend env is strict; missing variable will fail settings import in CI.
- Frontend env is strict; missing Vite vars fail tests/build.

## Validation Checklist
- Confirm command parity with local scripts.
- Ensure env keys mirror `.env.example` additions.

## Rollback Strategy
- Revert workflow changes quickly if PR gates deadlock.
- Reintroduce changes incrementally with isolated failing stage.

## Real Example
- Add `RAG_READY_TIMEOUT_MS` and ingestion env keys to backend CI job when they become required.
