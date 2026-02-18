# SLA/SLO and Error Budget

## Proposed SLOs

- API availability (monthly): 99.9%
- `/api/ask/stream/` first-byte latency p95: < 8s
- Auth success rate p99: > 99.5%

## Error Budget

- Monthly error budget for availability: 43.2 minutes
- On budget burn > 50%, freeze non-critical feature releases.
