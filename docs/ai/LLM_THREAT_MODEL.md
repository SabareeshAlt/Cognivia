# LLM Threat Model (AcademeRAG)

## Assets
- Source academic documents
- Retrieval index and metadata
- Prompt templates and system instructions
- Model responses and citations
- API tokens and tenant context

## Trust Boundaries
1. Browser client -> Django API
2. Django API -> retrieval/vector services
3. Django API -> model provider/runtime
4. Logging/observability sinks

## Primary Abuse Paths
- Prompt injection via untrusted document content.
- Data exfiltration through generated responses.
- Authorization bypass on protected endpoints.
- Denial-of-service through high-cost prompts.
- Insecure tool invocation (future function/tool calling).

## Required Controls
- JWT auth on generation endpoints.
- Endpoint rate limits and payload caps.
- Citation and grounding checks for responses.
- Per-request trace IDs and auditable logs.
- CI eval gates for quality regression.
- Supply chain controls (SBOM + vulnerability scans).

## Validation Checklist
- [ ] Prompt injection test corpus executed.
- [ ] Unauthorized request tests pass.
- [ ] Release blocked on eval-gate failures.
- [ ] Incident response playbook tested.
