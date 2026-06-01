"""
database/embedding.py
---------------------
OllamaEmbeddings wrapper for bge-m3:latest.
All modules that need to embed text should import from here.
"""

import logging
import time
from typing import List

from langchain_ollama import OllamaEmbeddings
from database.config import EMBEDDING_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

_EMBED_MAX_RETRIES = 3
_EMBED_RETRY_DELAY = 1.0


def get_embeddings() -> OllamaEmbeddings:
    """Return a configured OllamaEmbeddings instance for the active embedding model."""
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


def embed_documents_with_retry(embeddings: OllamaEmbeddings, texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts with automatic retry on transient failures."""
    last_exc = None
    for attempt in range(1, _EMBED_MAX_RETRIES + 1):
        try:
            return embeddings.embed_documents(texts)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Embedding attempt %d/%d failed: %s", attempt, _EMBED_MAX_RETRIES, exc
            )
            if attempt < _EMBED_MAX_RETRIES:
                time.sleep(_EMBED_RETRY_DELAY * attempt)
    raise RuntimeError(
        f"All {_EMBED_MAX_RETRIES} embedding attempts failed"
    ) from last_exc


def get_embedding_dimension(embeddings: OllamaEmbeddings) -> int:
    """Probe the embedding dimension by embedding a short sentinel string."""
    return len(embeddings.embed_query("dimension probe"))
