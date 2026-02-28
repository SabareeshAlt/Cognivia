# Django Frontend Integration Guide: Final.html

## Overview
This guide integrates your `Final.html` frontend with the Django backend through proper URL routing and static file serving.

---

## Step 1: Configure Django Settings

Update `rag_project/settings.py` to serve static files and the HTML template:

```python
# Add to INSTALLED_APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'api',
    'corsheaders',
]

# Add CORS middleware at the top
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Template configuration (ADD THIS)
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # Point to templates directory
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# CORS Settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOWED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1:3000',
    'http://localhost:3000',
]
```

---

## Step 2: Create Templates and Static Directories

Run these commands in your Project directory:

```bash
mkdir -p templates static/css static/js static/images
cp Final.html templates/index.html
```

---

## Step 3: Update URLs Configuration

### rag_project/urls.py

```python
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),  # Serve Final.html at root
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
```

### api/urls.py (Already correct)

```python
from django.urls import path
from . import views

urlpatterns = [
    path('ask/', views.ask_question, name='ask_question'),
    path('stream/', views.stream_answer, name='stream_answer'),
    path('health/', views.health_check, name='health_check'),
    path('model-info/', views.model_info, name='model_info'),
]
```

---

## Step 4: Update Final.html API Endpoint

The Final.html already has the correct API endpoint, but ensure it's using the correct URL:

**Current (in Final.html around line 550):**
```javascript
const response = await fetch('http://127.0.0.1:8000/api/ask/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
});
```

**Alternative (relative URL - recommended for production):**
```javascript
const response = await fetch('/api/ask/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
});
```

---

## Step 5: Create Static Files Directory Structure

```
Project/
├── static/
│   ├── css/
│   └── js/
├── templates/
│   └── index.html (copy of Final.html)
├── api/
├── rag_project/
├── manage.py
└── ...
```

---

## Step 6: Run Django Development Server

```bash
# Navigate to Project directory
cd /Users/apple/Applications/Visual Studio Code/Project

# Install dependencies (if not already done)
pip install django djangorestframework django-cors-headers

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver 0.0.0.0:8000
```

**Access the application at:** `http://127.0.0.1:8000`

---

## Step 7: Complete API Views Setup

Ensure your `api/views.py` has all required views:

```python
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt, require_http_methods
import json
import logging

logger = logging.getLogger(__name__)

# Initialize your RAG service here
# from rag_service import create_academic_rag_service
# rag_service = create_academic_rag_service()

@require_http_methods(["POST"])
@csrf_exempt
def ask_question(request):
    """Handle POST requests to /api/ask/"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        question = data.get('question', '').strip()
        
        if not question:
            return JsonResponse(
                {"error": 'The "question" field is required', "success": False},
                status=400
            )
        
        # Call your RAG service here
        # answer = rag_service.answer_question(question)
        
        answer = "Sample response: " + question  # Replace with actual RAG logic
        
        return JsonResponse({
            "answer": answer,
            "sources": [],
            "success": True
        })
    except Exception as e:
        logger.error(f"Error: {e}")
        return JsonResponse(
            {"error": str(e), "success": False},
            status=500
        )

@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        "status": "healthy",
        "service": "AcademeRAG API"
    })

@require_http_methods(["GET"])
def model_info(request):
    """Get model information"""
    return JsonResponse({
        "model": "AcademeRAG",
        "version": "1.0",
        "description": "Knowledge-Grounded Academic Assistant"
    })

@require_http_methods(["POST"])
@csrf_exempt
def stream_answer(request):
    """Streaming endpoint for real-time responses"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        question = data.get('question', '').strip()
        
        def event_stream():
            # Stream response in chunks
            yield f"data: {json.dumps({'status': 'processing'})}\n\n"
            
            # Call your streaming RAG service here
            # for chunk in rag_service.stream_answer(question):
            #     yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            yield f"data: {json.dumps({'status': 'complete', 'answer': 'Sample answer'})}\n\n"
        
        return StreamingHttpResponse(
            event_stream(),
            content_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        return JsonResponse(
            {"error": str(e), "success": False},
            status=500
        )
```

---

## Step 8: Update Final.html for Production

Modify the fetch URL in Final.html (around line 550):

```javascript
// Option 1: Relative URL (recommended)
const response = await fetch('/api/ask/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
});

// Option 2: Absolute URL with variable
const API_URL = window.location.origin + '/api/ask/';
const response = await fetch(API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
});
```

---

## Testing the Integration

### 1. Start Django Server
```bash
cd /Users/apple/Applications/Visual Studio Code/Project
python manage.py runserver
```

### 2. Test API Endpoint
```bash
curl -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Django?"}'
```

### 3. Access Frontend
Open browser: `http://127.0.0.1:8000`

---

## Troubleshooting

### 502 Bad Gateway / Connection Refused
- Ensure Django server is running: `python manage.py runserver`
- Check if port 8000 is available

### CORS Errors
- Verify `corsheaders` is installed
- Check CORS settings in `settings.py`
- Ensure middleware order is correct

### Template Not Found
- Verify `templates/index.html` exists
- Check `TEMPLATES['DIRS']` in settings

### Static Files Not Loading
- Run: `python manage.py collectstatic`
- Check `STATICFILES_DIRS` configuration

---

## Project Structure After Integration

```
Project/
├── api/
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   ├── views.py
│   └── migrations/
├── rag_project/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   └── index.html (Final.html)
├── static/
│   ├── css/
│   ├── js/
│   └── images/
├── manage.py
├── db.sqlite3
├── requirements.txt
└── rag_service.py
```

---

## Next Steps

1. **Connect RAG Service**: Update `api/views.py` to use your actual RAG service
2. **Implement Streaming**: Use the streaming endpoint for real-time responses
3. **Add Authentication**: Implement proper user authentication instead of hardcoded credentials
4. **Production Deployment**: Use Gunicorn/Uvicorn with Nginx reverse proxy

---

## Quick Reference Commands

```bash
# Create templates directory
mkdir -p templates

# Copy Final.html to templates
cp Final.html templates/index.html

# Install dependencies
pip install django djangorestframework django-cors-headers

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver

# Collect static files
python manage.py collectstatic

# Run tests
python manage.py test api
```

---

**Status**: Ready for integration with your RAG backend!
