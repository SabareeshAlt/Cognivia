# Enterprise Audit Report (Phase 1)

Date: 2026-02-18  
Scope: AcademeRAG full-stack architecture, RAG pipeline, security, CI/DevOps, frontend, observability, performance, enterprise readiness.

## Method

Parallel sub-agent audits were executed across six tracks (backend+performance, RAG, security, DevOps+enterprise readiness, frontend, observability). Findings were normalized by severity and mapped to concrete implementation upgrades.

## Critical Findings

1. Missing metrics/tracing platform (backend + frontend)
- Area: Observability
- Evidence: No OpenTelemetry/Prometheus instrumentation; frontend telemetry is in-memory only.
- Risk: No SLO/error-budget governance, no latency/error distributions, low incident diagnosability.
- Upgrade:
  - Add Prometheus metrics endpoint (`/api/metrics`) with request latency histograms, RAG retrieval latency, LLM latency counters.
  - Add OTel tracing hooks for API, vector query, and LLM calls.
  - Propagate `trace_id` into all response paths including streaming events.

## High Findings

1. Retriever cache lifecycle can pin stale/failed RAG state
- Area: RAG Pipeline
- Evidence: Cached retriever path can prevent rebuild/recovery without process restart.
- Risk: Corpus changes or ingestion failures may not recover quickly and can degrade availability.
- Upgrade:
  - Cache only after successful initialization.
  - Invalidate cache when tracked corpus hash/chunk profile changes.
  - Add explicit cache-reset + rebuild management command.

2. Rebuild path is destructive before ingestion success
- Area: RAG Pipeline
- Evidence: Collection drop/recreate occurs before full ingest success.
- Risk: Failed ingest can leave no usable index.
- Upgrade:
  - Two-phase indexing with temp collection + atomic swap on success.
  - Rollback-safe failure path and state persistence only after full success.

3. Refresh token rotation lacks revocation semantics
- Area: Security
- Evidence: Rotation enabled but blacklist/reuse prevention not enabled.
- Risk: Stolen refresh tokens remain replayable until expiry.
- Upgrade:
  - Enable `rest_framework_simplejwt.token_blacklist` and `BLACKLIST_AFTER_ROTATION=True`.
  - Track session/device metadata and revoke on suspicious refresh reuse.

4. Prompt-injection resistance is insufficient
- Area: Security / RAG
- Evidence: User question enters prompt without explicit injection refusal policy.
- Risk: Instruction override and hallucination/inappropriate behavior.
- Upgrade:
  - Add injection guardrails (policy + regex/heuristic classifier).
  - Add refusal-on-override logic before LLM invocation.

5. CI backend validation and artifact/provenance checks are incomplete
- Area: DevOps/CI
- Evidence: Missing strict checks expected in enterprise baseline.
- Risk: Drift, unverified artifacts, reduced supply-chain assurance.
- Upgrade:
  - Add `manage.py check`, static checks, migration consistency checks.
  - Add reproducible artifact/SBOM/signing job.
  - Add live RAG eval/perf smoke gate.

## Medium Findings

1. Readiness semantics are stale/limited
- Area: Backend/Observability
- Evidence: async cache-based readiness with limited dependency metadata.
- Risk: false healthy/degraded signals and poor operator diagnostics.
- Upgrade:
  - Return dependency-specific reason codes + latency + last check times.
  - Add bounded synchronous probe option with cache TTL.

2. Inconsistent error trace payloads
- Area: Backend API
- Evidence: Not all error responses include `trace_id`.
- Risk: weak log-to-user correlation.
- Upgrade:
  - Standardize all error responses through helper adding `trace_id`.

3. Frontend streaming contract is untyped
- Area: Frontend architecture
- Evidence: raw text stream handling in UI without event envelope.
- Risk: brittle protocol evolution and weaker error semantics.
- Upgrade:
  - Move stream parser to API client and expose typed stream events.

4. CORS/credential configuration can be misconfigured
- Area: Security
- Evidence: insecure combinations possible if env flags drift.
- Risk: cross-origin abuse risk or broken browser behavior.
- Upgrade:
  - Hard-fail invalid combinations in settings.

5. Dependency pinning strategy not strict enough
- Area: Security/Supply chain
- Evidence: open ranges for critical deps.
- Risk: unplanned vulnerable upgrades.
- Upgrade:
  - Adopt lock/constraints strategy + CVE gates in CI.

## Low Findings

1. Runtime retrieval parameters are not externally visible
- Area: RAG/Operations
- Upgrade: expose active `top_k`, `chunk_size`, profile in diagnostics.

2. Frontend test coverage gaps on streaming and auth lifecycle
- Area: Frontend quality
- Upgrade: add targeted streaming/auth lifecycle unit+integration tests.

## Prioritized Upgrade Backlog (Phases 2-10)

1. Architecture
- Introduce service abstractions for vector store and LLM gateways.
- Separate orchestration (views) from domain services.

2. Security
- Refresh blacklist and session tracking.
- Prompt injection guard + input size/content policy checks.

3. Observability
- Metrics endpoint + histograms for request/retrieval/LLM durations.
- Structured JSON logging with redaction and trace propagation.

4. RAG hardening
- Two-phase safe index rebuild.
- Retrieval diagnostics endpoint (admin-only).
- Deterministic fallback regression tests.

5. Performance/Scalability
- Async/bounded streaming worker model.
- Load profile scripts and latency budgets.

6. CI/CD
- Coverage gates, SAST/secret scans, artifact validation/signing, perf regression checks.

7. Docs/Operations
- Threat model, attack surface, ADRs, SLO/SLA/error budget policy, rollback + incident runbook.

