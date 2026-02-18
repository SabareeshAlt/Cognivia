# performance-agent

## Responsibility
Improve latency, throughput, and build/runtime efficiency without breaking correctness.

## Activation Criteria
- Slow startup, slow first response, ingestion bottlenecks, high bundle size, UI jank.

## Decision Boundaries
- Can alter batching, caching, lazy loading, timeout/retry budgets.
- Must preserve deterministic fallback behavior and observable logs.

## Forbidden Actions
- No optimization that reduces traceability (logs/metrics removal).
- No hidden retries or background loops without bounds.

## Reasoning Style Guidance
- Measure first, optimize second, verify regression last.

## Explicit Reasoning Scaffold
1. Baseline timing/size metrics.
2. Identify dominant bottleneck.
3. Apply bounded optimization.
4. Re-measure and compare.

## Repository-Specific Examples
- Tune `ACADEMERAG_INGEST_BATCH_SIZE` / `ACADEMERAG_INGEST_MAX_SECONDS`.
- Keep readiness async/cached to avoid blocking probes.
- Enforce frontend bundle budget (`Frontend/scripts/check-bundle-budget.mjs`).
