"""
Deprecated compatibility shim.

Canonical retrieval implementation lives in Milvus.py.
"""

from Milvus import (  # noqa: F401
    get_pdf_files,
    initialize_vector_store,
    get_optimized_response,
    stream_optimized_response,
    compute_sync_decision,
)


def get_retriever(k=3):
    store = initialize_vector_store(force_reindex=False)
    if not store:
        return None
    return store.as_retriever(search_type="similarity", search_kwargs={"k": int(k)})


def get_rag_chain():
    raise RuntimeError(
        "vector.get_rag_chain() is deprecated. Use Milvus.get_optimized_response() APIs."
    )
