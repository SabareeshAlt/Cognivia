# Skill: add-migration

## When To Use
- Changing Django models in `api/models.py`.

## Preconditions
- Model contract change is finalized.
- Backward compatibility expectations are known.

## Step-by-Step Plan
1. Edit `api/models.py`.
2. Generate migration: `python manage.py makemigrations api`.
3. Review migration file for destructive operations.
4. Apply migration locally: `python manage.py migrate`.
5. Add/update tests for new model behavior.

## Edge Cases In This Repo
- Ingestion tracking model (`IndexedDocument`) drives rebuild decisions; careless changes can force unnecessary reindex.
- Keep indexes aligned with frequent query filters.

## Validation Checklist
- `python manage.py migrate`
- `python manage.py test`
- Ensure `api/migrations/*.py` is committed.

## Rollback Strategy
- Add reverse migration if already shared.
- If local-only, revert model and migration file.

## Real Example
- Add field to `IndexedDocument` and update filters in `Milvus.py` accordingly.
