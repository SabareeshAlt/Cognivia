# Security Policy

## Reporting

Report security issues privately to project maintainers. Do not open public issues for active vulnerabilities.

## Security Controls

- JWT auth enforced on protected ask endpoints.
- API rate limiting enabled for auth and ask routes.
- Request trace IDs (`X-Request-ID`) propagated for incident forensics.
- Refresh token rotation enabled with blacklist-on-rotation.
- CORS credentials mode guarded against wildcard origin misconfiguration.

## Secure Configuration Requirements

- Set `DJANGO_DEBUG=false` in production.
- Use strong `DJANGO_SECRET_KEY` and secret managers for all credentials.
- Keep `CORS_ALLOW_ALL_ORIGINS=false` when credentials are enabled.
- Restrict `DJANGO_ALLOWED_HOSTS` to production domains.
- Enforce HTTPS via `SECURE_SSL_REDIRECT=true` and non-zero HSTS.

## Operational Security Checklist

- Run `pip-audit` and `npm audit --audit-level=high` in CI.
- Run secret scanning in CI (gitleaks).
- Review auth-refresh and high-rate abuse logs weekly.
- Rotate Milvus/Ollama credentials periodically.

