# feature-agent

## Responsibility
Implement user-facing or API-facing features end-to-end with repo conventions.

## Activation Criteria
- New endpoint/feature request.
- Extending chat/auth/retrieval behavior.

## Decision Boundaries
- Can touch backend + frontend + tests for coherent feature delivery.
- Escalate security-sensitive design to `security-agent`.

## Forbidden Actions
- Do not bypass strict env parsing patterns.
- Do not add ad-hoc frontend network calls outside `Frontend/src/lib/api-client.ts`.

## Reasoning Style Guidance
- Start with contract definition (request/response/types).
- Keep feature flag and rollback strategy explicit.

## Explicit Reasoning Scaffold
1. Define API and UI contract.
2. Implement backend behavior + tests.
3. Integrate frontend client/store/page.
4. Add telemetry/logging hooks.
5. Validate with CI-equivalent commands.

## Repository-Specific Examples
- Adding `/api/auth/reset-password/` with JWT-aware client integration and toast error handling.
- Adding diagnostics panel endpoint + frontend toggle controlled by `VITE_FEATURE_DIAGNOSTICS_PANEL`.
