"""
database/reranker.py
--------------------
CrossEncoder lazy-load and document reranking pipeline.
"""

import logging
import os
import threading
from typing import List

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()


def _get_cross_encoder():
    """Lazy-load the CrossEncoder model (double-checked locking)."""
    global _cross_encoder_model
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                logger.info("Initializing CrossEncoder model for reranking...")
                try:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    from sentence_transformers import CrossEncoder
                    _cross_encoder_model = CrossEncoder(
                        "BAAI/bge-reranker-v2-m3", local_files_only=True
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to initialize CrossEncoder in offline mode: %s. "
                        "Retrying in online mode...", exc
                    )
                    try:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                        from sentence_transformers import CrossEncoder
                        _cross_encoder_model = CrossEncoder("BAAI/bge-reranker-v2-m3")
                    except ImportError:
                        logger.error(
                            "sentence_transformers is not installed. "
                            "CrossEncoder reranking will fail."
                        )
                        raise
    return _cross_encoder_model


def preload_cross_encoder() -> None:
    """Eagerly load the CrossEncoder model to avoid lazy-loading on first request."""
    try:
        _get_cross_encoder()
    except Exception as exc:
        logger.warning("Failed to preload CrossEncoder: %s", exc)


def _cross_encoder_rerank(
    query: str, docs: List[Document], k: int
) -> List[Document]:
    """Rerank documents using the CrossEncoder model."""
    if not docs:
        return []
    try:
        model = _get_cross_encoder()
    except ImportError:
        return docs[:k]

    pairs = [[query, doc.page_content] for doc in docs]
    scores = model.predict(pairs)

    scored_docs = list(zip(docs, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)

    reranked_docs = []
    cutoff = float(os.environ.get("ACADEMERAG_RERANK_CUTOFF", "0.3"))
    for doc, score in scored_docs:
        if float(score) < cutoff:
            continue
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rerank_score"] = float(score)
        reranked_docs.append(doc)
        if len(reranked_docs) >= k:
            break

    return reranked_docs
