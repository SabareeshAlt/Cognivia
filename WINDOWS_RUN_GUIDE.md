# AcademeRAG Windows Deployment & Execution Guide

This guide outlines the steps required to configure, verify, and run the AcademeRAG system on a Windows platform.

---

## Prerequisites

1. **Python 3.9+** (Ensure Python is added to the system PATH).
2. **Node.js 18+** (Required for compiling and running the React frontend).
3. **Ollama** (Required for local/offline inference with `gemma3:12b` or `llama3.2`).
   - Download and install Ollama from [ollama.com](https://ollama.com).
   - Pull the required model in PowerShell:
     ```powershell
     ollama pull gemma3:12b
     ollama pull llama3.2
     ```
4. **Git** (Required for code tracking and version checks).

---

## Workspace Setup

1. **Clone the Repository** and navigate to the project root:
   ```powershell
   cd "C:\Sabareesh\AcademeRAG - Research\AcademeRAG-Final"
   ```

2. **Initialize Python Virtual Environment**:
   ```powershell
   python -m venv .venv
   ```

3. **Activate the Environment**:
   ```powershell
   .\venv\Scripts\activate
   ```

4. **Install Backend Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

5. **Install Frontend Dependencies**:
   ```powershell
   cd Frontend
   npm install
   cd ..
   ```

---

## Configuration

Modify the `.env` file in the root directory to customize the runtime behaviors. Key properties to verify:

```ini
# Environment settings
DJANGO_SECRET_KEY=local-development-secret-key-at-least-thirty-two-chars
RAG_WARMUP_ON_STARTUP=true

# Milvus Database (Milvus Lite local file or Zilliz Cloud URI)
ACADEMERAG_MILVUS_URI=./milvus_local.db
ACADEMERAG_MILVUS_TOKEN=
COLLECTION_NAME=AcademeRAG

# Offline LLM config
OLLAMA_MODEL_NAME=gemma3:12b
OLLAMA_BASE_URL=http://localhost:11434
```

---

## Execution

To launch both the Django backend and React frontend simultaneously with automated startup verification, run:

```powershell
.\venv\Scripts\activate
python main.py
```

### Verification Logs

Upon running `main.py`, the system verifies configurations and displays a status checklist:

```text
AcademeRAG Booting...
✓ Environment Loaded
✓ Milvus Connected
✓ BM25 Ready
✓ Embeddings Loaded
✓ Retriever Ready
✓ Knowledge Base Loaded

✓ Backend Running
✓ Frontend Running

AcademeRAG started successfully
```

Press `Ctrl+C` in the terminal to cleanly terminate all backend, frontend, and database services.

---

## Running Verification Tests

To verify environment integrity, execute the automated test suites:

* **Backend Tests**:
  ```powershell
  python manage.py test
  ```
* **Frontend Tests**:
  ```powershell
  cd Frontend
  npm run test
  ```
