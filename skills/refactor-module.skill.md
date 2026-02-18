# Skill: refactor-module

## When To Use
- Internal cleanup or decomposition without intended contract changes.

## Preconditions
- Existing behavior is covered by tests or can be quickly captured.

## Step-by-Step Plan
1. Identify module boundary and exported contract.
2. Add/confirm tests around current behavior.
3. Move/extract code in small steps.
4. Keep imports stable or provide compatibility shim.
5. Remove dead code after references are zero.

## Edge Cases In This Repo
- `Milvus.py` is canonical retrieval path; avoid creating parallel retrieval logic.
- `vector.py` currently acts as compatibility shim and should stay lightweight.

## Validation Checklist
- `python manage.py test`
- `cd Frontend && npm run test` if client contract affected.

## Rollback Strategy
- Revert extraction commit.
- Restore compatibility imports immediately if breakage occurs.

## Real Example
- Refactor readiness helper internals in `api/views.py` while preserving endpoint response schema.
