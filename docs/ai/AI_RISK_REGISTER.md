# AI Risk Register

## Purpose
Track GenAI/RAG-specific risks, owners, mitigations, and residual risk acceptance.

## Risk Table
| ID | Risk | Category | Likelihood | Impact | Owner | Mitigation | Residual Risk | Review Date |
|---|---|---|---|---|---|---|---|---|
| AIR-001 | Prompt injection leads to unsafe instructions | Model Security | Medium | High | AI Reliability | Instruction hierarchy, allow-listed tools, retrieval source trust labels | Medium | 2026-03-01 |
| AIR-002 | Hallucinated response without citation | Quality | High | High | AI Reliability | Eval gates, citation enforcement, response policy checks | Medium | 2026-03-01 |
| AIR-003 | Sensitive data leakage in logs | Privacy | Low | High | Platform | Redaction pipeline, least-privilege log access, retention controls | Low | 2026-03-01 |
| AIR-004 | Cost explosion from abusive queries | Availability/Cost | Medium | Medium | Platform | Rate limits, request budgets, anomaly alerts | Low | 2026-03-01 |

## Governance Cadence
- Weekly risk review (engineering + security).
- Monthly executive sign-off on unresolved high risks.
- Every incident must map to one or more risk IDs.
