# Enterprise-Grade Upgrade Report V2
## AcademeRAG - Enterprise Readiness for a GenAI Product

**Generated:** February 17, 2026  
**Project:** AcademeRAG (Django + React/Vite RAG Platform)  
**Baseline Source:** `ENTERPRISE_UPGRADE_REPORT.md`  
**Primary Goal:** Upgrade from prototype maturity to enterprise-grade reliability, governance, and scalability.

---

## 1) Critical Analysis of V1 Plan

### What V1 got right
- Broad domain coverage (security, infra, testing, observability, documentation).
- Practical stack choices (PostgreSQL, Redis, CI/CD, OpenAPI, Playwright, Sentry).
- Good intent around phased rollout and measurable outcomes.

### Major gaps in V1
- Enterprise web security is addressed; **GenAI risk controls are not** (prompt injection, model abuse, unsafe tool usage, grounding integrity).
- Test strategy is generic; **RAG quality gates are missing** (faithfulness, grounding, citation correctness, retrieval precision).
- Observability is ops-oriented; **LLM-native trace semantics are missing** (prompt/retrieval/rerank/generation spans, token economics, safety outcomes).
- CI/CD exists; **software supply-chain trust is incomplete** (SBOM, signing, provenance attestation, deploy policy checks).
- Roadmap sequencing over-prioritizes infrastructure (Kubernetes/microservices) before AI reliability/governance controls.

### Reframe for enterprise standard
Enterprise readiness for a GenAI product requires all of the following before scale-out:
1. Secure app foundations.
2. AI governance + threat model.
3. RAG evaluation gates in CI and release workflows.
4. Production telemetry with GenAI semantics.
5. Supply-chain integrity and auditable change management.

---

## 2) Updated Priority Model

### P0 (Blocker) - Must be complete before production go-live
- Identity, session, API security, secret management, tenant isolation baseline.
- AI risk management profile and LLM threat model.
- RAG evaluation framework with hard release gates.
- Observability baseline with end-to-end traceability.
- Supply-chain security baseline.

### P1 (High) - Complete in first 30-45 days post-baseline
- Hybrid retrieval + reranking pipeline.
- Cost and latency optimization with SLOs.
- Comprehensive incident response and runbooks.
- Compliance automation and audit evidence pipelines.

### P2 (Scale/Optimization) - After reliability controls are stable
- Multi-region architecture.
- Controlled service decomposition.
- Advanced personalization, automation, and adaptive retrieval.

---

## 3) Enterprise Architecture Upgrades (New)

### 3.1 AI Governance and Risk Controls (NEW P0)
**Objective:** Prevent unsafe behavior and make AI risk auditable.

**Tasks**
- Create an AI control matrix mapped to NIST AI RMF + Generative AI Profile.
- Build a product-specific LLM threat model using OWASP LLM risk categories.
- Define model usage policies: allowed tasks, disallowed content classes, escalation paths.
- Add prompt injection defenses: instruction hierarchy, source trust tagging, tool-call allow-lists.
- Implement human override and kill-switch procedures for unsafe behavior.

**Acceptance Criteria**
- Signed-off AI risk register with owner per risk.
- Threat scenarios documented with mitigations and residual risk rating.
- Incident playbook tested in tabletop exercise with timestamped evidence.

### 3.2 RAG Quality Engineering (NEW P0)
**Objective:** Prevent silent quality regression.

**Tasks**
- Create a curated golden evaluation set per academic domain.
- Add offline eval metrics:
  - Retrieval: Recall@k, NDCG@k, MRR.
  - Generation: groundedness, citation precision, faithfulness, answer completeness.
- Add CI quality gates for prompt/retrieval/model/config changes.
- Add canary + shadow evaluation in production before full rollout.
- Version datasets, prompts, retrievers, rerankers, and model configs.

**Acceptance Criteria**
- Every release has a machine-readable eval report.
- Deploy blocked automatically if gates fail.
- Rollback procedure validated by one controlled canary failure test.

### 3.3 Observability 2.0 (NEW P0/P1)
**Objective:** Debug and optimize full RAG lifecycle.

**Tasks**
- Instrument full trace path: API -> retrieval -> rerank -> generation -> post-processing.
- Capture GenAI telemetry attributes: model ID, token counts, latency, per-step costs, safety outcome.
- Log citation provenance IDs and retrieval scores for each answer.
- Define dashboards by user journey and by incident class.
- Alert on SLO burn rates, hallucination proxy spikes, and cost anomalies.

**Acceptance Criteria**
- Trace coverage >95% on production requests.
- P95 latency and error budget visible in real-time dashboards.
- On-call can identify failing pipeline stage within 10 minutes.

### 3.4 Supply-Chain Security (NEW P0)
**Objective:** Ensure deployable artifacts are trusted and auditable.

**Tasks**
- Generate SBOM for backend/frontend images.
- Sign container images and verify signatures at deployment.
- Emit provenance attestations in CI.
- Add policy checks: block deploy for critical CVEs or unsigned artifacts.
- Add dependency update cadence with approval workflow.

**Acceptance Criteria**
- 100% production artifacts are signed and verifiable.
- Admission policy rejects non-compliant artifacts.
- Security report generated on every release.

### 3.5 Data Governance and Tenant Controls (NEW P0/P1)
**Objective:** Enable enterprise procurement and compliance.

**Tasks**
- Implement per-tenant data boundaries and authorization checks.
- Add per-tenant encryption strategy and key rotation policy.
- Add retention/deletion workflows with evidence artifacts.
- Add data lineage: source document -> embedding -> retrieval -> response citation.
- Add legal hold and export workflows.

**Acceptance Criteria**
- Tenant isolation penetration tests pass.
- Deletion request generates auditable completion evidence.
- Data lineage query supported for any served answer.

---

## 4) Retrieval/Model Pipeline Advancements (Beyond V1)

### 4.1 Hybrid Retrieval + Reranking (P1)
- Combine lexical retrieval (BM25/FTS) + vector retrieval.
- Add cross-encoder reranking for top-k candidate refinement.
- Use dynamic retrieval strategy by query intent/type.

**Expected impact:** higher relevance, fewer hallucinations, better citation hit-rate.

### 4.2 Query Planning and Decomposition (P1)
- Split complex questions into sub-queries.
- Aggregate evidence with conflict resolution and confidence scoring.
- Return transparent citation mapping for each claim.

### 4.3 Advanced Corpus Strategies (P2)
- Add graph-aware retrieval for relationship-heavy corpora.
- Add temporal filters/version-aware retrieval for policy-like documents.
- Add source trust weighting and freshness-aware reranking.

---

## 5) Revised Delivery Plan

## Phase 0 (Week 0-1): Baseline Hardening and Decision Gates
- Finalize architecture decision records (ADR) for auth, DB, retrieval, observability.
- Enforce branch protections, commit signing policy, CODEOWNERS.
- Define SLOs/SLIs and release criteria.

## Phase 1 (Week 1-3): P0 Enterprise Foundations
- Complete app security baseline (auth, CSRF, rate limits, secrets, TLS).
- Stand up PostgreSQL + managed backups + disaster recovery runbook.
- Implement AI governance, LLM threat model, incident workflow.
- Ship initial RAG evaluation harness and CI quality gates.
- Add foundational telemetry and tracing.
- Enable SBOM/signing/provenance + deploy policy checks.

## Phase 2 (Week 4-6): Reliability and Performance
- Hybrid retrieval + reranking rollout.
- SLO dashboards, alert tuning, on-call runbooks.
- Cache strategy and async job framework for heavy pipelines.
- Expand test pyramid (unit/integration/E2E/load/chaos-lite).

## Phase 3 (Week 7-10): Compliance and Enterprise Readiness
- Tenant isolation verification.
- Data retention/deletion/export/legal hold controls.
- Audit evidence automation and compliance report generation.
- Security and AI red-team exercises with remediation closure.

## Phase 4 (Week 11-14): Scale-out
- Controlled multi-region setup and failover tests.
- Capacity planning and autoscaling policy validation.
- Evaluate service decomposition only for validated bottlenecks.

---

## 6) KPIs and Enterprise Gates (Updated)

### Security and Governance
- Zero critical open vulns in deployable artifacts.
- 100% signed artifacts and provenance attestation.
- Mean time to remediate high severity < 7 days.

### RAG Quality
- Citation precision >= 95% on golden set.
- Groundedness >= 90% on golden set.
- Retrieval NDCG@10 improvement vs baseline by >= 15%.
- Regression gate: block release if any key metric drops > 3% from approved baseline.

### Reliability and Performance
- API availability >= 99.9%.
- P95 response latency <= 1.2s for standard query class.
- P99 <= 2.5s with controlled degradation strategy.

### Operational Excellence
- MTTR < 30 minutes for Sev-2 incidents.
- 100% production incidents have postmortems within 3 business days.
- Cost per successful answer tracked and trended weekly.

---

## 7) Concrete Backlog Additions to Apply Now

### Add to current report as new tasks
- **TASK 1.10 (P0):** AI Risk Register + Governance Controls.
- **TASK 1.11 (P0):** LLM Threat Modeling + Red-Team Test Suite.
- **TASK 5.6 (P0):** End-to-End GenAI Trace Instrumentation.
- **TASK 6.6 (P0):** RAG Evaluation Harness + CI Release Gates.
- **TASK 2.7 (P0):** SBOM + Artifact Signing + Provenance Attestation.
- **TASK 10.4 (P1):** Tenant Isolation Verification and Data Lineage Controls.
- **TASK 4.5 (P1):** Hybrid Retrieval + Cross-Encoder Reranking.
- **TASK 6.7 (P1):** Canary/Shadow Deployment for Prompt/Retriever/Model Changes.

### Sequencing correction
Do not treat Kubernetes/microservices as required for enterprise grade before P0 AI governance/evals/traceability are live.

---

## 8) Team Topology and Ownership

### Recommended ownership model
- **Platform team:** CI/CD, observability, infra, supply chain.
- **AI reliability team:** retrieval quality, eval harness, prompt/model governance.
- **Application team:** product features, UX, tenant controls, API contract stability.
- **Security/compliance function:** policy, audits, incident response, control verification.

### Minimum staffing to hit plan
- 1 Platform Engineer
- 1 Backend Engineer
- 1 Frontend Engineer
- 1 ML/AI Engineer (shared acceptable)
- 0.5 Security Engineer (shared or fractional)

---

## 9) Final Verdict

V1 is a strong general modernization plan. It is **not yet enterprise-grade for a GenAI/RAG system** because it lacks AI-specific governance, evaluation gates, supply-chain trust, and traceable model/retrieval operations.

This V2 closes those gaps and reorders delivery to reduce risk first, then scale.

