# ADR-001: Canonical Retrieval Module

Status: Accepted

## Context

Repository previously had multiple retrieval implementations, increasing drift and operational risk.

## Decision

`Milvus.py` is the canonical retrieval + ingestion implementation.

## Consequences

- All retrieval behavior changes must land in `Milvus.py`.
- API layer (`api/views.py`) only orchestrates and does not duplicate retrieval logic.
