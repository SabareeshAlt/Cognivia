# Quick Reference - Django Frontend Integration + Project Overview

## 🚀 NEW: Django Frontend Integration

### Start the Server (3 Steps)
```bash
cd "/Users/apple/Applications/Visual Studio Code/Project"
python manage.py runserver
# Open: http://127.0.0.1:8000
```

### Login Credentials
- **Username**: `admin`
- **Password**: `12345`

### Essential URLs
| URL | Purpose |
|-----|---------|
| `http://127.0.0.1:8000` | Frontend (Final.html) |
| `http://127.0.0.1:8000/api/ask/` | Ask Question |
| `http://127.0.0.1:8000/api/health/` | Health Check |

### Test API
```bash
curl -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Django?"}'
```

### Documentation
- Full guide: `DJANGO_FRONTEND_INTEGRATION.md`
- Testing: `TESTING_GUIDE.md`
- Status: `INTEGRATION_COMPLETE.md`

---

## 📚 Original Quick Navigation

### Documentation Files
| File | Purpose | Read Time |
|------|---------|-----------|
| `PROJECT_ANALYSIS_REPORT.md` | Full project analysis with improvements | 15 min |
| `IMPLEMENTATION_SUMMARY.md` | What was changed and why | 10 min |
| `SETUP_GUIDE.md` | How to run the project | 5 min |
| `DJANGO_FRONTEND_INTEGRATION.md` | Django frontend integration | 8 min |
| `TESTING_GUIDE.md` | Testing and troubleshooting | 10 min |

---

## Common Tasks

### 1. Run CLI
```bash
cd Project
python main.py
```

### 2. Start Django API
```bash
cd Project
python manage.py runserver 0.0.0.0:8000
```

### 3. Run Gradio UI
```bash
cd Project
python -m gradio Gradio.py
```

### 4. Call API
```bash
# Standard request
curl -X POST http://localhost:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "Your question"}'

# Stream response
curl -N "http://localhost:8000/api/stream/?question=Your%20question"
```

### 5. Add PDFs
```bash
# Create documents folder
mkdir -p Project/documents

# Copy PDFs there
cp path/to/pdf.pdf Project/documents/

# Force reload in Python
from streaming_vector import initialize_vector_store
vector_store, retriever = initialize_vector_store(force_reload=True)
```

---

## New Modules - Quick Reference

### `rag_service.py` - RAG Logic

**Main Class**: `RAGService`

```python
from rag_service import create_academic_rag_service

# Create service
rag = create_academic_rag_service()

# Validate input
is_valid, error = rag.validate_input(question)

# Answer question
answer = rag.answer_question(question, docs)

# Stream answer
async for token in rag.stream_answer(question, docs):
    print(token, end='')
```

**Preset Services**:
- `create_academic_rag_service()` - For academic content (temp=0.3)
- `create_conversational_rag_service()` - For chat (temp=0.7)
- `create_detailed_rag_service()` - For detailed answers (temp=0.5)

**Builder Pattern**:
```python
from rag_service import RAGChainBuilder

rag = RAGChainBuilder() \
    .with_model("llama3.2") \
    .with_temperature(0.5) \
    .build()
```

---

### `streaming_vector.py` - Vector Store

**Main Classes**:

1. **StreamingPDFProcessor**
```python
from streaming_vector import StreamingPDFProcessor

processor = StreamingPDFProcessor(chunk_size=800, overlap=100)

# Stream chunks from PDF
for chunk in processor.stream_pdf_chunks("file.pdf"):
    print(f"Chunk: {chunk[:100]}")

# Stream from multiple PDFs
for chunk, source in processor.stream_all_pdfs(pdf_paths):
    print(f"{source}: {chunk[:100]}")
```

2. **StreamingVectorStore**
```python
from streaming_vector import StreamingVectorStore, StreamingPDFProcessor

processor = StreamingPDFProcessor()
store = StreamingVectorStore(batch_size=50)

# Add documents streaming
count = store.add_documents_streaming(processor, pdf_paths)
print(f"Added {count} documents")

# Get retriever
retriever = store.get_retriever(k=5)
```

3. **Module-level Function**
```python
from streaming_vector import initialize_vector_store

# Standard initialization
vector_store, retriever = initialize_vector_store()

# With custom PDFs
vector_store, retriever = initialize_vector_store(pdf_paths=[...])

# Force reload
vector_store, retriever = initialize_vector_store(force_reload=True)
```

---

## API Endpoints

### POST `/api/ask/` - Standard Response
```bash
curl -X POST http://localhost:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about X"}'
```

**Response**:
```json
{
  "answer": "Full answer text...",
  "sources": ["file1.pdf", "file2.pdf"],
  "success": true,
  "document_count": 3
}
```

---

### GET `/api/stream/` - Streaming Response
```bash
curl -N "http://localhost:8000/api/stream/?question=Tell%20me%20about%20X"
```

**Server-Sent Events (SSE)** Response:
```
event: token
data: "Generated"

event: token
data: " token"

event: done
data: {"success": true}
```

---

### GET `/api/health/` - Health Check
```bash
curl http://localhost:8000/api/health/
```

**Response**:
```json
{
  "status": "healthy",
  "rag_service": true,
  "retriever": true,
  "timestamp": "2025-12-31T10:00:00"
}
```

---

### GET `/api/model-info/` - Model Details
```bash
curl http://localhost:8000/api/model-info/
```

**Response**:
```json
{
  "model_name": "llama3.2",
  "temperature": 0.3,
  "status": "ready"
}
```

---

## Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Core settings
OLLAMA_MODEL_NAME=llama3.2
MILVUS_URI=./milvus_local.db
CHUNK_SIZE=800

# Django
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1

# Feature flags
ENABLE_STREAMING=True
LOG_LEVEL=INFO
```

Load in Python:
```python
import os
from dotenv import load_dotenv

load_dotenv()
model_name = os.getenv("OLLAMA_MODEL_NAME")
chunk_size = int(os.getenv("CHUNK_SIZE", "800"))
```

---

## Logging

All modules use Python's built-in logging:

```python
import logging

logger = logging.getLogger(__name__)

# Automatically used in:
# - rag_service.py
# - streaming_vector.py
# - api/views.py
# - main.py
```

**Configure logging**:
```python
import logging

logging.basicConfig(
    level=logging.DEBUG,  # DEBUG, INFO, WARNING, ERROR
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
```

---

## Error Handling

All functions have proper error handling:

```python
from rag_service import RAGService

rag = RAGService()

try:
    # Input validation
    is_valid, error = rag.validate_input(question)
    if not is_valid:
        raise ValueError(error)
    
    # Answer generation
    answer = rag.answer_question(question, docs)

except ValueError as e:
    print(f"Input error: {e}")  # Bad question
except TimeoutError as e:
    print(f"Timeout: {e}")       # Model too slow
except Exception as e:
    print(f"Error: {e}")         # Other errors
```

---

## Performance Tips

### 1. Batch Processing
```python
# Bad - Load all at once
docs = [Document(...) for _ in range(10000)]
vector_store.add_documents(docs)

# Good - Batch in smaller chunks
for i in range(0, len(docs), 50):
    batch = docs[i:i+50]
    vector_store.add_documents(batch)
```

### 2. Caching Retrievals
```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_retriever():
    return initialize_vector_store()[1]
```

### 3. Streaming Long Responses
```python
# Use stream endpoint instead of standard
# Saves memory and shows progress to user
curl -N "http://localhost:8000/api/stream/?question=..."
```

### 4. Smaller Model for Speed
```python
from rag_service import RAGChainBuilder

# Fast response (2-3 seconds)
fast_rag = RAGChainBuilder() \
    .with_model("mistral:latest") \
    .with_temperature(0.3) \
    .build()

# Quality response (5-10 seconds)
quality_rag = RAGChainBuilder() \
    .with_model("llama2:13b") \
    .build()
```

---

## Troubleshooting

### Issue: "Model not loaded"
```bash
# Check Ollama is running
curl http://localhost:11434/api/models

# Pull model if needed
ollama pull llama3.2
```

### Issue: "No documents in retriever"
```python
# Check if documents were added
from streaming_vector import initialize_vector_store
_, retriever = initialize_vector_store(force_reload=True)

# Verify documents exist
docs = retriever.invoke("test")
print(f"Found {len(docs)} documents")
```

### Issue: "Memory error on large PDF"
```python
# Reduce chunk size
from streaming_vector import StreamingVectorStore, StreamingPDFProcessor

processor = StreamingPDFProcessor(chunk_size=400)  # Reduce from 800
store = StreamingVectorStore(batch_size=25)        # Reduce from 50
```

### Issue: "Slow responses"
```python
# Check if streaming works
curl -N "http://localhost:8000/api/stream/?question=test"

# Use smaller model
# Check logs for errors
tail -f logs/app.log
```

---

## File Relationships

```
main.py
├── imports rag_service.py
│   ├── imports langchain
│   └── imports logging
└── imports streaming_vector.py
    ├── imports pypdf
    ├── imports langchain
    └── imports logging

api/views.py
├── imports rag_service.py
├── imports streaming_vector.py
├── imports django
└── imports logging

Gradio.py
├── imports rag_service.py
├── imports streaming_vector.py
└── imports gradio
```

---

## Code Examples

### Example 1: Basic RAG Usage
```python
from rag_service import create_academic_rag_service
from streaming_vector import initialize_vector_store

# Setup
rag = create_academic_rag_service()
_, retriever = initialize_vector_store()

# Ask question
question = "What is machine learning?"
docs = retriever.invoke(question)
answer = rag.answer_question(question, docs)
print(answer)
```

### Example 2: Streaming Response
```python
import asyncio
from rag_service import create_academic_rag_service
from streaming_vector import initialize_vector_store

async def stream_answer():
    rag = create_academic_rag_service()
    _, retriever = initialize_vector_store()
    
    question = "Explain deep learning"
    docs = retriever.invoke(question)
    
    async for token in rag.stream_answer(question, docs):
        print(token, end='', flush=True)

asyncio.run(stream_answer())
```

### Example 3: Custom RAG Service
```python
from rag_service import RAGChainBuilder

# Create specialized service
legal_rag = RAGChainBuilder() \
    .with_model("neural-chat") \
    .with_temperature(0.1) \  # Less creative
    .with_system_prompt("""
You are a legal assistant. Provide accurate legal information...
    """) \
    .build()

answer = legal_rag.answer_question(question, docs)
```

---

## Next Steps

1. **Test everything locally** - Run all three interfaces
2. **Load real PDFs** - Put docs in `documents/` folder
3. **Monitor performance** - Check logs during use
4. **Deploy to production** - Follow SETUP_GUIDE.md
5. **Gather feedback** - Improve based on usage

---

**Last Updated**: 2025-12-31  
**Questions?** Check the documentation files or logs
