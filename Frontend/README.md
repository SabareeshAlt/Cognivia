# AcademeRAG Frontend

Enterprise-focused React frontend for AcademeRAG (Vite + TypeScript + shadcn).

## Environment Variables

Create `Frontend/.env` from `Frontend/.env.example` and set:

- `VITE_API_BASE_URL` (optional; defaults to dynamic runtime resolution)
- `VITE_CHAT_DISABLED`
- `VITE_CANARY_PERCENT`
- `VITE_API_TIMEOUT_MS` (optional; defaults to `30000`)
- `VITE_MAX_JS_BUNDLE_KB`
- `VITE_FEATURE_ENHANCED_STREAMING`
- `VITE_FEATURE_DIAGNOSTICS_PANEL`

## Scripts

- `npm run dev`: start local dev server.
- `npm run test`: run Vitest unit/a11y/resilience tests.
- `npm run test:coverage`: run tests with coverage report.
- `npm run build`: production build.
- `npm run perf:budget`: enforce bundle-size budget from `VITE_MAX_JS_BUNDLE_KB`.
- `npm run test:e2e`: run Playwright critical path + visual regression.

## Enterprise Frontend Controls Implemented

- Typed API client with timeout/retry/error taxonomy.
- Feature flags + deterministic canary targeting + kill switch.
- Zustand workflow store for chat/session state.
- Route-level lazy loading and suspense fallback.
- Accessibility automation (`jest-axe`) and manual QA scripts in `Frontend/docs/`.
- Performance budget enforcement and web-vitals telemetry hooks.
- CSP/security headers in `Frontend/index.html` and `Frontend/public/_headers`.
