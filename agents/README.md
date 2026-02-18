# Agents Directory

This directory defines repository-specific sub-agents for task routing.

## Selection Rule
- Choose the narrowest agent whose activation criteria match the request.
- If multiple apply, run in this order:
  1. `architecture-agent.md` for boundary decisions.
  2. Domain agent (`backend-agent.md` / `frontend-agent.md` / `data-agent.md` / `api-agent.md`).
  3. Cross-cutting agent (`security-agent.md`, `performance-agent.md`, `test-agent.md`, `build-agent.md`, `devops-agent.md`).
  4. `refactor-agent.md` for structural changes.

## Shared Constraints
- Maintain env-driven configuration parity (`.env.example`, settings/config loaders, CI env).
- Preserve trace ID logging and rate-limit/auth patterns.
- Avoid parallel/duplicate retrieval implementations.
