# Component Maturity Model

## Tier 1: Primitives
- `src/components/ui/*`
- Must support keyboard navigation, visible focus, role/name/value semantics.
- No product-specific business logic.

## Tier 2: Composites
- `src/components/*` (non-`ui` components)
- Compose Tier 1 primitives into reusable app-level patterns.
- Must expose typed props and be unit tested.

## Tier 3: Product Modules
- `src/pages/*`, `src/store/*`, route-level orchestration.
- May contain product-specific behavior and workflow state.
- Must include integration tests and error-state handling.

## Review Checklist
- A11y: keyboard, focus trap, aria labels.
- Security: no unsafe HTML rendering.
- Performance: avoid unnecessary re-renders.
- Test coverage: unit for Tier 1/2, integration for Tier 3.
