"""
test_retrieval.py
Validates the AcademeRAG retrieval pipeline.
Tests Dense, BM25, and Hybrid retrieval across the new PDFs.
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

# We need to import the core engine from Milvus.py
try:
    from Milvus import (
        _search_cloud_milvus,
        _search_local_milvus,
        _search_bm25_fallback,
        _retrieve_docs,
        _get_cross_encoder,
        _cross_encoder_rerank
    )
    from langchain_ollama import OllamaEmbeddings
except ImportError as e:
    logger.error("Failed to import from Milvus.py: %s", e)
    sys.exit(1)

def print_results(label, docs):
    logger.info("=== %s ===", label)
    if not docs:
        logger.info("  No results found.")
    for i, doc in enumerate(docs[:3]):
        # doc can be a Document or a dict if returned by some pipelines
        meta = doc.metadata if hasattr(doc, 'metadata') else doc.get('metadata', {})
        text = doc.page_content if hasattr(doc, 'page_content') else doc.get('page_content', '')
        
        source = meta.get("source", "Unknown")
        page = meta.get("page_number", "?")
        score = meta.get("score", "N/A")
        logger.info("  %d. Source: %s (Page %s) | Score: %s", i+1, source, page, score)
        logger.info("     Snippet: %s...", text.replace('\n', ' ')[:100])
    logger.info("")

def run_tests():
    query = "What are the course objectives for computer networks?"
    logger.info("Testing Query: '%s'", query)
    
    # 1. Embed Query (for dense search)
    embeddings = OllamaEmbeddings(model=os.environ.get("EMBEDDING_MODEL", "bge-m3:latest"), base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    query_vector = embeddings.embed_query(query)
    logger.info("Generated query embedding of dim %d", len(query_vector))
    
    # 2. Dense Search (Zilliz)
    try:
        cloud_docs = _search_cloud_milvus(query_vector, query, k=5, target_sources=None)
        print_results("Dense Search (Zilliz Cloud)", cloud_docs)
    except Exception as e:
        logger.error("Dense Search (Zilliz) Failed: %s", e)

    # 3. Dense Search (Local Milvus)
    try:
        local_docs = _search_local_milvus(query_vector, query, k=5, target_sources=None)
        print_results("Dense Search (Local Milvus)", local_docs)
    except Exception as e:
        logger.error("Dense Search (Local) Failed: %s", e)

    # 4. Sparse Search (BM25)
    try:
        bm25_docs = _search_bm25_fallback(query, k=5, target_sources=None)
        print_results("Sparse Search (BM25 Fallback)", bm25_docs)
    except Exception as e:
        logger.error("Sparse Search (BM25) Failed: %s", e)
        
    # 5. Full Hybrid Pipeline + Reranking (via _retrieve_docs)
    try:
        hybrid_docs = _retrieve_docs(query)
        print_results("Hybrid Reranked Search (Full Pipeline)", hybrid_docs)
    except Exception as e:
        logger.error("Hybrid Search Pipeline Failed: %s", e)

if __name__ == "__main__":
    run_tests()
