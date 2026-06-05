# Report 1: Repository Audit Report

This report presents a complete scan and audit of the AcademeRAG repository to identify version-control clutter, duplicate files, security risks, and dependency status.

---

## 1. Clutter Findings (Version-Controlled Leftovers)

We detected a large volume of runtime artifacts and build files that are currently tracked under Git version control despite being present in `.gitignore`. This slows down repository operations and inflates metadata.

| File / Folder | Status | Path | Size | Reason for Clutter |
| :--- | :--- | :--- | :--- | :--- |
| **Virtual Environment** | Tracked | `.venv/` | ~340 MB | Local Python dependencies folder containing 12,585 files; should never be checked into version control. |
| **Frontend Coverage** | Tracked | `Frontend/coverage/` | ~2.4 MB | Vitest test coverage output reports containing HTML and JS assets; should be ignored. |
| **Playwright Report** | Tracked | `Frontend/playwright-report/index.html` | ~0.1 MB | E2E browser testing report generated dynamically; should be ignored. |
| **Python Bytecode Cache** | Tracked | `**/__pycache__/` | ~0.5 MB | Compiled Python bytecode files (`.pyc`) stored across app directories; should be ignored. |
| **Ingestion Logs** | Tracked | `ingest_pdfs.log`, `ingest_pdfs_bge_m3.log` | ~0.4 MB | Runtime execution logs generated during PDF ingestion; should be ignored. |

---

## 2. Duplicate Findings

- **Prometheus Metrics DBs**: Located in `prometheus_multiproc_dir/`. Multiple duplicate database files (`counter_*.db` and `histogram_*.db`) are generated dynamically during multi-process Django metrics tracking. These are transient runtime telemetry data and are already ignored by `.gitignore` (but we will verify they are not tracked).
- No duplicate source files or duplicated PDF datasets were found in `documents/`.

---

## 3. Dependency Analysis

### Python Dependencies
- **Requirements File**: [requirements.txt](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/requirements.txt) references [requirements_django.txt](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/requirements_django.txt).
- All packages (Django, langchain, pymilvus, etc.) are actively imported and required by the backend API and RAG pipelines.
- No obsolete or duplicate python packages are declared.

### Frontend Dependencies
- **Package Manifest**: [package.json](file:///c:/Sabareesh/AcademeRAG%20-%20Research/AcademeRAG-Final/Frontend/package.json).
- Declares Radix UI, Tanstack Query, framer-motion, lucide-react, and zustand, which are actively imported by React components.
- No unused npm packages or dead devDependencies were identified.

---

## 4. Security & Secret Audit

- **Hardcoded Secrets**: Scanned all tracked `.py`, `.ts`, `.tsx`, `.js`, and `.env` files for secrets, tokens, API keys, or credentials.
- **Result**: No hardcoded production credentials, API keys, or database passwords were found. Key environment configurations (such as `GROQ_API_KEY` or `ACADEMERAG_MILVUS_TOKEN`) are correctly loaded via `os.getenv` or `os.environ` from the local `.env` file, which is excluded from version control.
