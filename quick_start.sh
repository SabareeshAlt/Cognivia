#!/bin/bash
# Quick Start Script for AcademeRAG

echo ""
echo "============================================================"
echo "🎓 AcademeRAG - Quick Start"
echo "============================================================"
echo ""
echo "This will initialize your RAG system with 3 simple commands."
echo ""

# Check if Ollama is running
if ! curl -s http://localhost:11434 > /dev/null 2>&1; then
    echo "⚠️  Ollama is not running!"
    echo ""
    echo "Please start Ollama first:"
    echo "  ollama serve"
    echo ""
    exit 1
fi

echo "✅ Ollama is running"
echo ""

# Step 1: Setup Milvus
echo "Step 1: Setting up Milvus vector store..."
echo "----------------------------------------"
python3 setup_milvus.py

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Setup failed. Please check the errors above."
    exit 1
fi

echo ""
echo "============================================================"
echo "✅ Setup Complete!"
echo "============================================================"
echo ""
echo "Now run these commands in separate terminals:"
echo ""
echo "Terminal 1 - Backend:"
echo "  python3 manage.py runserver 0.0.0.0:8000"
echo ""
echo "Terminal 2 - Frontend:"
echo "  cd Frontend && npm run dev"
echo ""
echo "Then open: http://localhost:8080"
echo ""
