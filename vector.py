"""
AcademeRAG Vector Store Module
Handles PDF chunking with overlap and Milvus indexing
"""

import os
from pypdf import PdfReader
from langchain_ollama import OllamaEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document

# Project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# List of all 4 PDF files in the Project folder
pdf_paths = [
    os.path.join(PROJECT_ROOT, "RAG sample 1.pdf"),
    os.path.join(PROJECT_ROOT, "RAG sample 2.pdf"),
    #os.path.join(PROJECT_ROOT, "RAG sample 3.pdf"),
    os.path.join(PROJECT_ROOT, "RAG sample 4.pdf"),
]

# Chunking configuration
CHUNK_SIZE = 800
CHUNK_OVERLAP = 200


def pdfs_to_chunks(pdf_paths, chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP):
    """
    Extract text from PDFs and split into overlapping chunks.
    
    Args:
        pdf_paths: List of PDF file paths
        chunk_size: Size of each chunk (default: 800)
        chunk_overlap: Overlap between chunks (default: 200)
    
    Returns:
        List of tuples (chunk_text, source_filename)
    """
    all_chunks = []
    step = chunk_size - chunk_overlap  # 800 - 200 = 600
    
    for path in pdf_paths:
        if not os.path.exists(path):
            print(f"Warning: PDF not found: {path}")
            continue
            
        source = os.path.basename(path)
        print(f"Processing: {source}")
        
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        # Split text into overlapping chunks
        for i in range(0, len(text), step):
            chunk = text[i:i + chunk_size]
            if chunk.strip():  # Only add non-empty chunks
                all_chunks.append((chunk, source))
        
        print(f"  Extracted {len(text)} chars from {source}")
    
    print(f"Total chunks created: {len(all_chunks)}")
    return all_chunks


# Initialize Ollama Embeddings model
print("Initializing embeddings model...")
embeddings = OllamaEmbeddings(model="mxbai-embed-large")

# Milvus database URI and collection name
milvus_uri = os.path.join(PROJECT_ROOT, "milvus_local.db")
collection_name = "AcademeRAG"

# FORCE RE-INDEX: Set to True to re-index documents
FORCE_REINDEX = True

# Check whether to add documents
add_documents = FORCE_REINDEX or not os.path.exists(milvus_uri)

# Delete old database if force re-indexing
if FORCE_REINDEX and os.path.exists(milvus_uri):
    print("Removing old database for re-indexing...")
    os.remove(milvus_uri)
    # Also remove lock file if exists
    lock_file = milvus_uri + ".lock"
    if os.path.exists(lock_file):
        os.remove(lock_file)

# Initialize Milvus vector store
print("Initializing Milvus vector store...")
vector_store = Milvus(
    collection_name=collection_name,
    embedding_function=embeddings,
    connection_args={"uri": milvus_uri},
)

# Add documents to the vector store
if add_documents:
    print("Indexing PDFs into vector store...")
    chunks_with_sources = pdfs_to_chunks(pdf_paths)
    
    # Create documents with metadata
    documents = [
        Document(page_content=chunk, metadata={"source": source})
        for chunk, source in chunks_with_sources
    ]
    
    print(f"Adding {len(documents)} documents to vector store...")
    vector_store.add_documents(documents, drop_old=True)
    print("Indexing complete!")
else:
    print("Using existing vector store")

# Create retriever with top 5 results returned for queries
retriever = vector_store.as_retriever(search_kwargs={"k": 5})
print("Vector store ready!")
