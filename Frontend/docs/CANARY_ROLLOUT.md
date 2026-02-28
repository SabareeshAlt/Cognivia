# Frontend Canary Rollout

## Strategy
- `VITE_CANARY_PERCENT` controls deterministic percentage rollout.
- Bucket is derived from authenticated email hash.
- Emergency overrides can be applied via `localStorage.rag_feature_overrides`.

## Rollout
1. Deploy with `VITE_CANARY_PERCENT=5`.
2. Observe telemetry and error rate for 24h.
3. Increase to 25, 50, then 100 if stable.

## Rollback
1. Set `VITE_CHAT_DISABLED=true` for immediate kill switch.
2. Or disable specific features via override object.
3. Redeploy stable baseline.
