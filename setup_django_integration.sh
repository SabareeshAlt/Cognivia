#!/bin/bash

# Django Frontend Integration Setup Script
# This script sets up the Django project to serve Final.html as the frontend

echo "=========================================="
echo "AcademeRAG - Django Frontend Integration"
echo "=========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Navigate to Project directory
PROJECT_DIR="/Users/apple/Applications/Visual Studio Code/Project"
cd "$PROJECT_DIR" || exit 1

echo "📁 Working directory: $PROJECT_DIR"
echo ""

# Step 1: Create directories if they don't exist
echo "📂 Creating directory structure..."
mkdir -p templates static/css static/js static/images
echo "✓ Directories created"
echo ""

# Step 2: Copy Final.html to templates
echo "📋 Copying Final.html to templates..."
cp Final.html templates/index.html
echo "✓ index.html created in templates/"
echo ""

# Step 3: Install dependencies
echo "📦 Installing Python dependencies..."
pip install -q django djangorestframework django-cors-headers langchain-ollama langchain-milvus pypdf langchain-core 2>/dev/null || {
    echo "⚠️  Some packages may already be installed"
}
echo "✓ Dependencies installed"
echo ""

# Step 4: Run migrations
echo "🔄 Running Django migrations..."
python3 manage.py migrate --noinput
echo "✓ Migrations completed"
echo ""

# Step 5: Collect static files
echo "🎨 Collecting static files..."
python3 manage.py collectstatic --noinput 2>/dev/null || {
    echo "⚠️  Static files collection skipped (may already exist)"
}
echo "✓ Static files processed"
echo ""

# Step 6: Display final instructions
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "📖 Next Steps:"
echo ""
echo "1. Start the Django development server:"
echo "   python3 manage.py runserver"
echo ""
echo "2. Open your browser and navigate to:"
echo "   http://127.0.0.1:8000"
echo ""
echo "3. Default login credentials:"
echo "   Username: admin"
echo "   Password: 12345"
echo ""
echo "4. To test the API endpoint:"
echo "   curl -X POST http://127.0.0.1:8000/api/ask/ \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"question\": \"What is Django?\"}'"
echo ""
echo "📚 Project Structure:"
echo "   Project/"
echo "   ├── templates/"
echo "   │   └── index.html (Final.html)"
echo "   ├── static/"
echo "   │   ├── css/"
echo "   │   ├── js/"
echo "   │   └── images/"
echo "   ├── api/"
echo "   │   ├── views.py (API endpoints)"
echo "   │   └── urls.py"
echo "   ├── rag_project/"
echo "   │   ├── settings.py"
echo "   │   ├── urls.py"
echo "   │   └── wsgi.py"
echo "   └── manage.py"
echo ""
echo "🔗 API Endpoints:"
echo "   POST   /api/ask/          - Ask a question"
echo "   POST   /api/stream/       - Stream answer (SSE)"
echo "   GET    /api/health/       - Health check"
echo "   GET    /api/model-info/   - Model information"
echo "   GET    /                  - Frontend (Final.html)"
echo ""
echo "=========================================="
