# Threat Model

## Assets

- User auth tokens and account identity
- Document corpus and embeddings
- Retrieval outputs and generated answers
- Service availability for chat and ingestion

## Trust Boundaries

- Browser <-> API boundary
- API <-> Ollama boundary
- API <-> Milvus Cloud boundary
- CI/CD <-> repository/secrets boundary

## Key Threats

1. Token theft/replay
- Mitigations: refresh rotation, blacklist on rotation, rate limits, trace logging.

2. Prompt injection
- Mitigations: deterministic no-context fallback, guarded retrieval prompts, planned injection filter hardening.

3. Cross-origin abuse
- Mitigations: strict CORS origin list, no wildcard with credentials.

4. Supply-chain compromise
- Mitigations: dependency audits, SBOM generation, secret scanning.

5. Availability degradation
- Mitigations: health probes, bounded timeouts, ingestion limits, metrics and alerting.

