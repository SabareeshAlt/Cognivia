# Django Frontend Integration - Testing Guide

## Quick Start

### 1. Initial Setup
```bash
cd /Users/apple/Applications/Visual Studio Code/Project

# Install dependencies
pip install -r requirements_django.txt

# Run migrations
python manage.py migrate

# Start Django server
python manage.py runserver
```

### 2. Access the Application
- **Frontend**: Open browser to `http://127.0.0.1:8000`
- **Admin Panel**: `http://127.0.0.1:8000/admin`

### 3. Test Login
- **Username**: `admin`
- **Password**: `12345`

---

## API Endpoint Testing

### Test 1: Health Check
```bash
# Verify API is running
curl http://127.0.0.1:8000/api/health/

# Expected response:
# {
#   "status": "healthy",
#   "service": "AcademeRAG API",
#   "version": "1.0"
# }
```

### Test 2: Get Model Info
```bash
# Get model information
curl http://127.0.0.1:8000/api/model-info/

# Expected response:
# {
#   "model": "AcademeRAG",
#   "version": "1.0",
#   "description": "Knowledge-Grounded Academic Assistant",
#   "capabilities": [...]
# }
```

### Test 3: Ask Question (Non-Streaming)
```bash
# Test the ask endpoint
curl -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What is machine learning?"}'

# Expected response:
# {
#   "answer": "Sample response...",
#   "sources": [],
#   "success": true
# }
```

### Test 4: Stream Answer
```bash
# Test the streaming endpoint
curl -X POST http://127.0.0.1:8000/api/stream/ \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain artificial intelligence"}' \
  -N

# Watch for Server-Sent Events streaming
```

---

## Browser Console Testing

### Using the RAG Client Library
```javascript
// Open browser console and test the client

// Initialize client
const client = new RAGClient();

// Test 1: Health check
await client.healthCheck();

// Test 2: Ask question
const response = await client.askQuestion("What is Django?");
console.log(response);

// Test 3: Stream answer
client.streamAnswer(
  "Explain Python",
  (chunk) => console.log("Chunk:", chunk),
  () => console.log("Done"),
  (error) => console.error("Error:", error)
);
```

---

## Troubleshooting

### Issue: Connection Refused
```
Error: Failed to connect to the AI core
```

**Solution:**
1. Ensure Django server is running: `python manage.py runserver`
2. Check if port 8000 is in use: `lsof -i :8000`
3. Kill process if needed: `kill -9 <PID>`
4. Restart server

### Issue: CORS Error
```
Access to XMLHttpRequest blocked by CORS policy
```

**Solution:**
- Verify `CORS_ALLOW_ALL_ORIGINS = True` in `settings.py`
- Check middleware order: `CorsMiddleware` should be at top
- Restart Django server

### Issue: Template Not Found
```
TemplateDoesNotExist: index.html
```

**Solution:**
```bash
# Verify templates directory exists
ls -la templates/

# Verify index.html is present
ls -la templates/index.html

# Check settings.py has correct TEMPLATES['DIRS']
grep -A 5 "TEMPLATES = " rag_project/settings.py
```

### Issue: Static Files Not Loading
```
GET http://127.0.0.1:8000/static/... 404
```

**Solution:**
```bash
# Create static directories
mkdir -p static/css static/js static/images

# Collect static files
python manage.py collectstatic

# Or disable static file check in development
# Add to settings.py:
# STATIC_URL = '/static/'
```

### Issue: Port Already in Use
```
Error: Address already in use (:8000)
```

**Solution:**
```bash
# Use a different port
python manage.py runserver 8001

# Or kill the process using port 8000
lsof -i :8000
kill -9 <PID>
```

---

## Performance Testing

### Load Testing with ApacheBench
```bash
# Install Apache tools (macOS)
brew install httpd

# Test with 100 concurrent requests
ab -n 100 -c 10 http://127.0.0.1:8000/api/health/

# Test POST endpoint
ab -n 50 -c 5 -p post_data.json \
  -T application/json \
  http://127.0.0.1:8000/api/ask/
```

### Create `post_data.json`:
```json
{"question": "What is artificial intelligence?"}
```

---

## Frontend Integration Testing

### Test 1: Manual Question Submit
1. Open `http://127.0.0.1:8000`
2. Login with `admin` / `12345`
3. Type: "What is machine learning?"
4. Click "TRANSMIT" button
5. Verify response appears in chat

### Test 2: Multiple Questions
```
Q1: What is Python?
Q2: Explain decorators
Q3: What is a REST API?
```

### Test 3: Error Handling
1. Try submitting empty question - should show error
2. Disconnect server - should show connection error
3. Reload page - should retain session

---

## Debug Mode

### Enable Django Debug Mode
```python
# In settings.py
DEBUG = True
```

### View Django Logs
```bash
# Run with verbose output
python manage.py runserver --verbosity 2

# Check Python logs
tail -f /tmp/django.log
```

### Use Django Shell
```bash
python manage.py shell

# Test your RAG service
from rag_service import create_academic_rag_service
rag = create_academic_rag_service()
result = rag.answer_question("What is Django?")
print(result)
```

---

## Production Testing

### Using Gunicorn
```bash
# Install gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn rag_project.wsgi:application --bind 0.0.0.0:8000

# Run with multiple workers
gunicorn rag_project.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Using Whitenoise for Static Files
```bash
pip install whitenoise

# In settings.py, add to MIDDLEWARE:
MIDDLEWARE = [
    'whitenoise.middleware.WhiteNoiseMiddleware',
    # ...other middleware...
]
```

---

## Checklist for Integration Completion

- [ ] Django server starts without errors
- [ ] Frontend loads at `http://127.0.0.1:8000`
- [ ] Login works with admin/12345
- [ ] Health check endpoint responds
- [ ] Ask question endpoint responds
- [ ] Chat interface displays responses
- [ ] Streaming endpoint works (optional)
- [ ] No CORS errors in console
- [ ] No template not found errors
- [ ] Static files load correctly
- [ ] API responses contain correct data

---

## Next Steps

1. **Integrate RAG Service**
   - Update `api/views.py` to use actual RAG service
   - Uncomment RAG initialization code
   - Test with real queries

2. **Implement Proper Authentication**
   - Replace hardcoded credentials
   - Use Django authentication system
   - Add user registration

3. **Add Database Models**
   - Store conversation history
   - Track user queries
   - Cache responses

4. **Deploy to Production**
   - Use Gunicorn/Nginx
   - Set up SSL/TLS
   - Configure environment variables
   - Use PostgreSQL instead of SQLite

---

**Status**: All integration components are ready for testing!
