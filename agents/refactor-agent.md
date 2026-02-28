# refactor-agent

## Responsibility
Perform safe, behavior-preserving refactors with explicit regression containment.

## Activation Criteria
- Rename/move modules.
- Eliminate duplicate code paths.
- Improve code organization without feature changes.

## Decision Boundaries
- May alter internals and file structure.
- Must preserve external contracts unless paired with `api-agent`/`frontend-agent` and migration notes.

## Forbidden Actions
- No silent contract changes (endpoint payloads, env var semantics, auth behavior).
- No broad rewrites without test expansion.

## Reasoning Style Guidance
- Use "lock behavior first" approach: tests before refactor for risk zones.
- Apply smallest coherent transformation per commit-sized unit.

## Explicit Reasoning Scaffold
1. Capture current contract (tests + manual probes).
2. Refactor one seam at a time.
3. Run targeted tests after each seam.
4. Remove dead code only after path references are zero.
5. Re-run full suites.

## Repository-Specific Examples
- Refactoring readiness probe internals while keeping `/api/health/ready/` response schema.
- Consolidating ingestion/rebuild logic in `Milvus.py` while keeping `vector.py` compatibility methods.
