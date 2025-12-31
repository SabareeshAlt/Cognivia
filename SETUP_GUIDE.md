# AcademeRAG Setup Guide

## Overview

This is a production-ready setup guide for the AcademeRAG system with the new streaming and improved architecture.

## Prerequisites

- Python 3.10+
- Ollama (for local LLM)
- 8GB+ RAM
- macOS/Linux/Windows

## Quick Start

### 1. Clone & Setup

```bash
cd /Users/apple/Applications/Visual\ Studio\ Code/Project
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Prepare PDFs

```bash
# Create documents folder and add PDFs
mkdir -p documents
# Copy your PDF files to the documents/ folder
```

### 4. Run Services

#### Option A: CLI (Command Line)
```bash
python main.py
```

#### Option B: Django API
```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

#### Option C: Gradio Web UI
```bash
python -m gradio Gradio.py
```

## Project Structure (New)

```
Project/
├── main.py                      # CLI Interface (NEW - improved)
├── Gradio.py                    # Gradio Web UI
├── rag_service.py              # NEW - Centralized RAG logic
├── streaming_vector.py         # NEW - Streaming PDF processing
├── vector.py                   # Legacy - deprecated
├── api/
│   ├── views.py               # NEW - Improved with streaming
│   ├── urls.py                # NEW - Complete API routes
│   ├── models.py
│   └── ...
├── rag_project/
│   ├── settings.py            # Django settings
│   ├── urls.py               
│   └── ...
├── requirements.txt            # NEW - Improved dependencies
├── .env.example               # NEW - Environment template
└── documents/                 # PDFs go here (NEW)
```

## API Endpoints

### 1. Ask Question (Standard)
```bash
curl -X POST http://localhost:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "Tell me about X"}'
```

Response:
```json
{
  "answer": "Generated answer...",
  "sources": ["file1.pdf", "file2.pdf"],
  "success": true,
  "document_count": 3
}
```

### 2. Stream Answer (Real-time)
```bash
curl -N http://localhost:8000/api/stream/?question=Tell%20me%20about%20X
```

Uses Server-Sent Events (SSE) to stream tokens in real-time.

### 3. Health Check
```bash
curl http://localhost:8000/api/health/
```

### 4. Model Info
```bash
curl http://localhost:8000/api/model-info/
```

## Key Improvements

### ✅ Memory Management
- **Before**: Loaded entire PDF into memory
- **After**: Streams PDF content with `StreamingPDFProcessor`
- **Benefit**: Can handle large PDFs (100MB+) without OOM

### ✅ Code Organization
- **Before**: RAG logic duplicated in 3 places
- **After**: Centralized in `RAGService` class
- **Benefit**: Single source of truth, easier maintenance

### ✅ Streaming Responses
- **Before**: User waited for entire response
- **After**: Tokens streamed in real-time via SSE
- **Benefit**: Better UX, shows progress immediately

### ✅ Error Handling
- **Before**: No error handling
- **After**: Comprehensive try-catch with logging
- **Benefit**: Better debugging and user feedback

### ✅ Security
- **Before**: CSRF disabled, secrets exposed
- **After**: CSRF enabled, secrets in .env
- **Benefit**: Production-ready security

## Configuration Options

### RAG Service

```python
from rag_service import RAGChainBuilder

# Custom RAG service
service = RAGChainBuilder() \
    .with_model("llama2:latest") \
    .with_temperature(0.5) \
    .with_system_prompt("Custom prompt...") \
    .build()
```

### Vector Store

```python
from streaming_vector import initialize_vector_store

# Load specific PDFs
pdfs = ["/path/to/file1.pdf", "/path/to/file2.pdf"]
vector_store, retriever = initialize_vector_store(pdf_paths=pdfs)

# Force reload
vector_store, retriever = initialize_vector_store(force_reload=True)
```

## Logging

All components log to:
- Console (configurable level)
- File: `./logs/app.log`

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Performance Tips

1. **Batch Processing**: Add documents in batches (50-100 at a time)
2. **Caching**: Consider caching frequent questions
3. **Model Selection**: Use smaller models for faster responses
4. **Vector DB**: Milvus is more scalable than Chroma

## Troubleshooting

### Issue: "Model not found"
```bash
# Install Ollama model
ollama pull llama3.2
```

### Issue: "No documents in vector store"
```bash
# Force reload documents
# In Python:
from streaming_vector import initialize_vector_store
vector_store, retriever = initialize_vector_store(force_reload=True)
```

### Issue: CSRF validation failed
```python
# In Django settings, add domain to CSRF_TRUSTED_ORIGINS
CSRF_TRUSTED_ORIGINS = ['http://localhost:3000']
```

### Issue: Out of Memory
- Reduce `BATCH_SIZE` in `.env`
- Reduce `CHUNK_SIZE`
- Use smaller Ollama model

## Production Deployment

1. **Set DEBUG=False** in settings.py
2. **Configure ALLOWED_HOSTS**
3. **Use environment variables** for secrets
4. **Set up SSL/HTTPS**
5. **Configure database** (PostgreSQL recommended)
6. **Set up monitoring** with Prometheus
7. **Use Gunicorn** for WSGI
8. **Configure Nginx** as reverse proxy

## Testing

```python
# Test RAG service
from rag_service import create_academic_rag_service
from langchain_core.documents import Document

service = create_academic_rag_service()
docs = [Document(page_content="Test content")]
answer = service.answer_question("Test question", docs)
print(answer)
```

## Contributing

When adding new features:
1. Add logging statements
2. Add error handling
3. Add type hints
4. Follow the existing patterns

## Support

For issues or questions:
1. Check logs in `./logs/app.log`
2. Review error messages
3. Verify PDF files are in `./documents/`
4. Ensure Ollama is running

---

**Last Updated**: 2025-12-31
