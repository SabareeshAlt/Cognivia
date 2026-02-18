# AI Incident Response Runbook

## Incident Classes
- Sev-1: Data leak, auth bypass, critical model safety failure.
- Sev-2: Major hallucination spike, severe latency, widespread user impact.
- Sev-3: Isolated quality degradation.

## Immediate Response
1. Capture `trace_id`, endpoint, and user/session scope.
2. Disable affected feature via frontend kill switch (`VITE_CHAT_DISABLED=true`) when needed.
3. Throttle endpoint or block abusive sources.
4. Roll back to previous known-good retrieval/prompt config.

## Investigation
1. Inspect request traces and logs for affected window.
2. Compare current deployment to last passing eval report.
3. Classify root cause: prompt, retrieval index, model change, infrastructure.

## Recovery and Closure
1. Confirm mitigation and monitor error/quality metrics for 24h.
2. Publish postmortem with owner and remediation actions.
3. Update AI risk register entries and preventive controls.
