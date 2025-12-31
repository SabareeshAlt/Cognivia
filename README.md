# RAG System with Django Backend

A complete RAG (Retrieval-Augmented Generation) system with a Django backend serving a modern frontend interface.

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- pip (Python package manager)
- Ollama (for local LLM inference)

### Setup Instructions

1. **Navigate to the Project folder:**
   ```bash
   cd "/Users/apple/Applications/Visual Studio Code/Project"
   ```

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements_django.txt
   ```

4. **Run database migrations:**
   ```bash
   python manage.py migrate
   ```

5. **Start the development server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

6. **Access the application:**
   Open your browser and visit: http://127.0.0.1:8000

## 📁 Project Structure

```
Project/
├── manage.py                    # Django management script
├── requirements_django.txt      # Python dependencies
├── db.sqlite3                   # SQLite database
├── milvus_local.db             # Vector store database
│
├── rag_project/                 # Django settings
│   ├── __init__.py
│   ├── settings.py             # Django configuration
│   ├── urls.py                 # URL routing
│   └── wsgi.py
│
├── api/                         # Django REST API app
│   ├── __init__.py
│   ├── admin.py
│   ├── models.py
│   ├── views.py                # API endpoints
│   └── urls.py                 # API URL routing
│
├── templates/                   # HTML templates
│   └── index.html              # Main frontend (served at /)
│
├── static/                      # Static files
│   └── js/
│       └── rag-client.js       # JavaScript API client
│
├── rag_service.py              # RAG service implementation
├── streaming_vector.py         # Vector store with streaming
├── vector.py                   # Vector store operations
└── Milvus.py                   # Milvus vector database
```

## 🔌 API Endpoints

### POST `/api/ask/`
Ask a question and get a RAG-powered response.

**Request:**
```json
{
    "question": "Your question here"
}
```

**Response:**
```json
{
    "answer": "Generated answer based on retrieved documents",
    "sources": ["source1.pdf", "source2.pdf"],
    "success": true
}
```

### POST `/api/stream/`
Get streaming responses (Server-Sent Events).

**Request:**
```json
{
    "question": "Your question here"
}
```

**Response:** Server-Sent Events stream

### GET `/api/health/`
Check API health status.

**Response:**
```json
{
    "status": "healthy",
    "rag_service": true,
    "retriever": false
}
```

### POST `/api/upload/`
Upload documents for RAG processing.

**Request:** multipart/form-data with file

### GET `/api/documents/`
List uploaded documents.

## 🎨 Frontend Features

- Modern, responsive UI
- Real-time chat interface
- Document upload capability
- Source citation display
- Streaming response support
- Dark/light mode (if implemented)

## ⚙️ Configuration

### Django Settings (`rag_project/settings.py`)

Key configurations:
- `DEBUG`: Set to `False` in production
- `ALLOWED_HOSTS`: Add your domain in production
- `CORS_ALLOWED_ORIGINS`: Configure for cross-origin requests
- `STATIC_URL`: Static files URL path
- `TEMPLATES`: Template directory configuration

### Environment Variables

Create a `.env` file (optional):
```
DEBUG=True
SECRET_KEY=your-secret-key
OLLAMA_MODEL=llama3.2:latest
```

## 🧪 Testing

### Test the API:
```bash
# Health check
curl http://127.0.0.1:8000/api/health/

# Ask a question
curl -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What is machine learning?"}'
```

### Run Django tests:
```bash
python manage.py test
```

## 🔧 Troubleshooting

### Vector Store Not Initializing
The error "milvus-lite is required" indicates Milvus Lite isn't installed. For local development without a full Milvus server:
```bash
pip install "pymilvus[model]"
```

### Ollama Not Running
Ensure Ollama is installed and running:
```bash
# Start Ollama
ollama serve

# Pull required model
ollama pull llama3.2:latest
```

### CORS Issues
If accessing from a different domain, ensure CORS is configured in `settings.py`:
```python
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

### Static Files Not Loading
Run collectstatic for production:
```bash
python manage.py collectstatic
```

## 📚 Documentation Files

- `README.md` - This file
- `DJANGO_FRONTEND_INTEGRATION.md` - Integration guide
- `TESTING_GUIDE.md` - Testing instructions
- `SETUP_GUIDE.md` - Detailed setup guide
- `STREAMING_IMPLEMENTATION_GUIDE.md` - Streaming implementation details

## 🚀 Production Deployment

1. Set `DEBUG=False` in settings
2. Configure proper `SECRET_KEY`
3. Set `ALLOWED_HOSTS`
4. Run collectstatic
5. Use gunicorn:
   ```bash
   gunicorn rag_project.wsgi:application --bind 0.0.0.0:8000
   ```

## 📄 License

This project is for educational and development purposes.

---

**Server Status:** Running at http://127.0.0.1:8000
