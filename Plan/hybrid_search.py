import threading
import logging
from typing import List, Tuple, Union
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Global state for lazy-loaded CrossEncoder
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()

def _rrf_fuse(dense_docs: List[Union[Document, Tuple[Document, float]]], 
              sparse_docs: List[Union[Document, Tuple[Document, float]]], 
              k: int) -> List[Document]:
    """
    Combine dense and sparse documents using Reciprocal Rank Fusion.
    score = 1 / (60 + rank)
    Deduplication is performed by (source, page_number, chunk_index).
    """
    def extract_doc(item: Union[Document, Tuple[Document, float]]) -> Document:
        return item[0] if isinstance(item, tuple) else item

    def doc_key(doc: Document) -> Tuple:
        metadata = doc.metadata or {}
        return (
            metadata.get("source"),
            metadata.get("page_number"),
            metadata.get("chunk_index"),
            doc.page_content if metadata.get("chunk_index") is None else None
        )

    rrf_scores = {}
    doc_map = {}

    # Rank and score dense docs
    for rank, item in enumerate(dense_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    # Rank and score sparse docs
    for rank, item in enumerate(sparse_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    # Sort documents by their RRF score in descending order
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # Retrieve the top k documents and update their metadata with the RRF score
    fused_docs = []
    for key in sorted_keys[:k]:
        doc = doc_map[key]
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rrf_score"] = rrf_scores[key]
        fused_docs.append(doc)

    return fused_docs

def _get_cross_encoder():
    """Lazy-load the CrossEncoder model."""
    global _cross_encoder_model
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                logger.info("Initializing CrossEncoder model for reranking...")
                try:
                    from sentence_transformers import CrossEncoder
                    # Standard efficient cross-encoder model
                    _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                except ImportError:
                    logger.error("sentence_transformers is not installed. CrossEncoder reranking will fail.")
                    raise
    return _cross_encoder_model

def _cross_encoder_rerank(query: str, docs: List[Document], k: int) -> List[Document]:
    """
    Rerank documents using a CrossEncoder model.
    """
    if not docs:
        return []
    
    try:
        model = _get_cross_encoder()
    except ImportError:
        # Fallback if cross-encoder is not available
        return docs[:k]
    
    # Prepare query-document pairs
    pairs = [[query, doc.page_content] for doc in docs]
    
    # Predict scores
    scores = model.predict(pairs)
    
    # Pair up docs and scores, then sort
    scored_docs = list(zip(docs, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)
    
    # Update metadata with the rerank score and return top k
    reranked_docs = []
    for doc, score in scored_docs[:k]:
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rerank_score"] = float(score)
        reranked_docs.append(doc)
        
    return reranked_docs

def _expand_neighbor_chunks(doc: Document, milvus_client, collection_name: str) -> List[Document]:
    """
    Query Milvus for neighboring chunks (i-1 and i+1) based on metadata filtering.
    """
    metadata = doc.metadata or {}
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    
    # If we don't have enough metadata to find neighbors, return the original doc
    if source is None or chunk_index is None:
        return [doc]
        
    target_indices = [chunk_index - 1, chunk_index + 1]
    target_indices = [i for i in target_indices if i >= 0]
    
    if not target_indices:
        return [doc]
        
    # Escape source string for the Milvus expression
    escaped_source = source.replace("\\", "\\\\").replace('"', '\\"')
    
    # Construct the PyMilvus query expression
    expr = f'source == "{escaped_source}" and chunk_index in {target_indices}'
    
    try:
        # Request all known metadata fields along with the text
        output_fields = ["text"] + list(metadata.keys())
        
        results = milvus_client.query(
            collection_name=collection_name,
            filter=expr,
            output_fields=output_fields
        )
        
        neighbors = []
        for res in results:
            text = res.pop("text", "")
            # Remove Milvus specific fields if they were fetched
            res.pop("pk", None)
            res.pop("vector", None)
            neighbors.append(Document(page_content=text, metadata=res))
            
        # Combine the original document with its neighbors
        all_docs = [doc] + neighbors
        
        # Sort by chunk_index to maintain reading order
        all_docs.sort(key=lambda x: x.metadata.get("chunk_index", 0))
        
        return all_docs
        
    except Exception as e:
        logger.warning("Failed to expand neighbor chunks for %s (index %s): %s", source, chunk_index, e)
        return [doc]
