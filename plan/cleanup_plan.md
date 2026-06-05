# Report 2: Cleanup Plan

This plan identifies safe and recommended Git operations to untrack version-controlled clutter without deleting the local files required for development.

---

## 1. Safe Removals (Untrack from Version Control only)

These files and folders match `.gitignore` rules but are currently tracked. Untracking them is safe because it only clears them from the Git index while preserving them locally.

| Item | Target Path | Command to Execute |
| :--- | :--- | :--- |
| **Virtual Env** | `.venv/` | `git rm -r --cached .venv` |
| **Vitest Coverage** | `Frontend/coverage/` | `git rm -r --cached Frontend/coverage` |
| **Playwright Report** | `Frontend/playwright-report/index.html` | `git rm --cached Frontend/playwright-report/index.html` |
| **Ingestion logs** | `*.log` | `git rm --cached ingest_pdfs.log ingest_pdfs_bge_m3.log` |
| **Bytecode Cache** | `**/__pycache__/` | `git rm -r --cached **/___pycache___` (done via app-level cache targets) |

---

## 2. Risky Removals (NOT Recommended)

We do **not** recommend deleting or untracking the following files, as they are required for running diagnostics, rebuilding collections, or executing test suites:
- `create_milvus_collection.py` (essential for setting up the Zilliz Cloud database)
- `rebuild_collection.py` (essential database migration utility)
- `test_generation.py` / `test_retrieval.py` (used in regression testing)
- `eval/golden_set.json` (fallback test cases)

---

## 3. Human Verification Items

- **Local Virtual Env Availability**: After running the Git untracking commands, verify that the `.venv/` folder is still intact locally and that `.venv/Scripts/python` executes normally.
