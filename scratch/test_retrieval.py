import os
import sys

# Setup django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")

import django
django.setup()

from Milvus import _retrieve_docs, _format_context, _augment_docs_for_syllabus

def test_retrieval():
    question = "What are the course objectives of machine learning?"
    print(f"Question: {question}")
    docs = _retrieve_docs(question)
    print(f"Retrieved {len(docs)} documents")
    
    docs = _augment_docs_for_syllabus(question, docs)
    print(f"After augmentation: {len(docs)} documents")
    
    context = _format_context(docs)
    print(f"Formatted context length: {len(context)} chars")
    
    # Print the source of each chunk in the context
    print("Chunks in context:")
    for i, doc in enumerate(docs):
        print(f"  {i}: source={doc.metadata.get('source')}, page={doc.metadata.get('page_number')}, index={doc.metadata.get('chunk_index')}")

if __name__ == "__main__":
    test_retrieval()
