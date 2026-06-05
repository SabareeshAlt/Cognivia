# Implementation Plan: Repository Cleanup & Decluttering Audit

This plan outlines the repository decluttering, directory inventory, and git tracking hygiene cleanup to optimize repository size, performance, and structure.

---

## Goal Description
Perform a repository-wide inventory audit to detect dead code, duplicate assets, and git tracking anomalies. Specifically, untrack directories and files that match `.gitignore` rules (such as `.venv/`, `Frontend/coverage/`, and log files) but were previously committed and tracked, which currently inflates the Git repository size by over 12,000 files.

---

## User Review Required

> [!IMPORTANT]
> **Git Untracking Safe Operations**:
> We will run `git rm -r --cached` on `.venv/`, `Frontend/coverage/`, `Frontend/playwright-report/index.html`, and temporary log files. 
> - **Note**: This will NOT delete these directories or files on your local machine. It only removes them from Git version control so they are no longer tracked in the repository.
> - On subsequent checkouts by other users, these files will not be pulled, which is standard production practice.

> [!WARNING]
> Running Git untracking requires a clean workspace or staged commits. We will stage all current validation framework files (`eval/multi_agent/`) so they are safely preserved.

---

## Open Questions

> [!NOTE]
> 1. Are there any specific files in the `prometheus_multiproc_dir/` directory (metrics tracking databases) that you want version-controlled, or should we untrack the entire directory as per the `.gitignore` rule?
> 2. Should we remove the root-level logs (`ingest_pdfs.log` and `ingest_pdfs_bge_m3.log`) completely from disk, or simply untrack them in Git?

---

## Proposed Changes

We will untrack ignored items currently in Git's index using cached removal and update the `.gitignore` to prevent any future tracking leaks. No backend logic, database schemas, or frontend UI structures will be modified, ensuring 100% preservation of RAG pipeline functionality.

### Git Hygiene & Cleanup Layer

#### [MODIFY] [.gitignore](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/.gitignore)
- Add entries for any missing temporary runtime artifacts and ensure proper patterns for cache folders.

#### [DELETE] [ingest_pdfs.log](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/ingest_pdfs.log) [from Git tracking only]
- Untrack and stop version-controlling the pipeline ingestion logs.

#### [DELETE] [ingest_pdfs_bge_m3.log](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/ingest_pdfs_bge_m3.log) [from Git tracking only]
- Untrack and stop version-controlling the model-specific ingestion logs.

#### [DELETE] [.venv/](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/.venv/) [from Git tracking only]
- Untrack the virtual environment packages directory (12,585 files) to clean up repository metadata.

#### [DELETE] [Frontend/coverage/](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/Frontend/coverage/) [from Git tracking only]
- Untrack the frontend Vitest unit test coverage report folder.

---

## Verification Plan

### Automated Tests
We will verify that:
1. Running `git status` after untracking lists the directories as ignored (not untracked or modified).
2. Django unit tests (`python manage.py test`) and Frontend Vitest suites (`npm run test`) continue to run successfully.
3. The local server starts and offline Ollama inference query pipelines operate correctly.

### Manual Verification
1. Verify that the `.venv/` directory remains present on disk and functional for local python execution.
