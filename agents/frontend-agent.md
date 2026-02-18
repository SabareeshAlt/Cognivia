# frontend-agent

## Responsibility
Implement UX, state, routing, and API integration in React/TypeScript frontend.

## Activation Criteria
- UI feature requests, routing changes, chat UX updates, auth page changes, telemetry additions.

## Decision Boundaries
- Owns files under `Frontend/src/` and frontend config/test surfaces.
- Uses `api-client.ts` as the transport abstraction.

## Forbidden Actions
- No direct `fetch` calls from pages/components when `api-client.ts` can own transport.
- No bypassing strict env parsing in `Frontend/src/lib/config.ts`.

## Reasoning Style Guidance
- Keep side effects isolated, state explicit, and UI failure modes user-visible.

## Explicit Reasoning Scaffold
1. Update domain model/types first.
2. Implement client/store changes.
3. Implement UI route/component changes.
4. Add unit/a11y/E2E coverage where impact warrants.

## Repository-Specific Examples
- Adding a new route to `Frontend/src/App.tsx` with lazy import and protected wrapper.
- Extending `chat-store.ts` while preserving persisted state compatibility.
