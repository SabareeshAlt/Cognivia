#!/usr/bin/env python3
"""
Setup script to initialize Milvus vector store with PDFs
This script will:
1. Create the documents directory
2. Copy PDFs from root to documents folder
3. Initialize Milvus vector store
4. Index all PDF documents
"""
import os
import shutil
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Milvus import initialize_vector_store, get_pdf_files, DOCUMENTS_DIR, PROJECT_ROOT

def print_banner(text):
    """Print a formatted banner."""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

def copy_pdfs():
    """Copy PDFs from root to documents folder."""
    print_banner("📂 Step 1: Copying PDFs to documents folder")
    
    # Ensure documents directory exists
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    print(f"✅ Documents directory: {DOCUMENTS_DIR}")
    
    pdf_files = [
        "RAG sample 1.pdf",
        "RAG sample 2.pdf",
        "RAG sample 3.pdf"
    ]
    
    copied = 0
    for pdf in pdf_files:
        src = os.path.join(PROJECT_ROOT, pdf)
        dst = os.path.join(DOCUMENTS_DIR, pdf)
        
        if os.path.exists(src):
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
                print(f"   ✅ Copied: {pdf}")
                copied += 1
            else:
                print(f"   ℹ️  Already exists: {pdf}")
                copied += 1
        else:
            print(f"   ⚠️  Not found: {pdf}")
    
    if copied == 0:
        print("\n❌ No PDFs found to copy!")
        print(f"💡 Please add PDF files to: {PROJECT_ROOT}")
        return False
    
    print(f"\n✅ {copied} PDF file(s) ready in documents folder")
    return True

def verify_pdfs():
    """Verify PDFs are accessible."""
    print_banner("📄 Step 2: Verifying PDF files")
    
    pdf_files = get_pdf_files()
    
    if not pdf_files:
        print("❌ No PDF files found!")
        print(f"   Searched in: {DOCUMENTS_DIR}")
        print(f"   Also checked: {PROJECT_ROOT}")
        return False
    
    print(f"✅ Found {len(pdf_files)} PDF file(s):")
    total_size = 0
    for pdf_path in pdf_files:
        size = os.path.getsize(pdf_path)
        total_size += size
        size_mb = size / (1024 * 1024)
        print(f"   📄 {os.path.basename(pdf_path):<30} ({size_mb:.2f} MB)")
    
    print(f"\n📊 Total size: {total_size / (1024 * 1024):.2f} MB")
    return True

def initialize_milvus():
    """Initialize Milvus vector store with PDFs."""
    print_banner("🚀 Step 3: Initializing Milvus Vector Store")
    
    print("⏳ This may take a few minutes depending on PDF size...")
    print("   - Loading PDFs")
    print("   - Extracting text")
    print("   - Creating chunks")
    print("   - Generating embeddings")
    print("   - Storing in Milvus")
    
    vector_store = initialize_vector_store(force_reindex=True)
    
    if vector_store:
        print_banner("✅ Setup Complete!")
        return True
    else:
        print_banner("❌ Setup Failed")
        return False

def main():
    """Main setup function."""
    print("\n" + "=" * 60)
    print("🎓 AcademeRAG Milvus Setup Wizard")
    print("=" * 60)
    print("\nThis script will set up your vector store for RAG queries.")
    print("Make sure Ollama is running: ollama serve")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        return
    
    # Step 1: Copy PDFs
    if not copy_pdfs():
        print("\n💡 Add PDF files and run this script again.")
        return
    
    # Step 2: Verify PDFs
    if not verify_pdfs():
        print("\n💡 Please check your PDF files and try again.")
        return
    
    # Step 3: Initialize Milvus
    success = initialize_milvus()
    
    if success:
        print("\n🎉 Your AcademeRAG system is ready!")
        print("\n📝 Next steps:")
        print("   1. Start Django server:")
        print("      python3 manage.py runserver 0.0.0.0:8000")
        print("\n   2. Start Frontend (in another terminal):")
        print("      cd Frontend && npm run dev")
        print("\n   3. Open browser:")
        print("      http://localhost:8080")
        print("\n✨ Happy querying!")
    else:
        print("\n❌ Setup incomplete. Please check the errors above.")
        print("\n💡 Common issues:")
        print("   - Is Ollama running? (ollama serve)")
        print("   - Are the models pulled?")
        print("     ollama pull llama3.2")
        print("     ollama pull mxbai-embed-large")
        print("   - Do you have PDF files?")

if __name__ == "__main__":
    main()
