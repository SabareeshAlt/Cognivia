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


import math

class NaNSafeOllamaEmbeddings(OllamaEmbeddings):
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        max_retries = 5
        retry_delay = 2.0
        
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return super().embed_documents(texts)
            except Exception as e:
                last_exc = e
                # Check if it's a NaN/500/Internal Server Error
                if "NaN" in str(e) or "500" in str(e) or "Internal Server Error" in str(e):
                    logger.warning("Batch embedding failed. Falling back to element-wise embedding with NaN protection.")
                    result = []
                    for text in texts:
                        item_vec = None
                        item_err = None
                        for item_attempt in range(1, max_retries + 1):
                            try:
                                item_vec = super().embed_documents([text])[0]
                                break
                            except Exception as item_exc:
                                item_err = item_exc
                                if "NaN" in str(item_exc) or "500" in str(item_exc):
                                    logger.warning(
                                        "Embedding failed for text: %r. Applying split-and-average NaN protection.",
                                        text[:100]
                                    )
                                    words = text.split()
                                    if len(words) > 1:
                                        h1 = " ".join(words[:len(words)//2])
                                        h2 = " ".join(words[len(words)//2:])
                                        try:
                                            r1 = super().embed_documents([h1])[0]
                                            r2 = super().embed_documents([h2])[0]
                                            avg = [(x + y) / 2.0 for x, y in zip(r1, r2)]
                                            norm = math.sqrt(sum(x * x for x in avg))
                                            if norm > 0:
                                                item_vec = [x / norm for x in avg]
                                            else:
                                                item_vec = avg
                                            break
                                        except Exception as split_err:
                                            logger.error("Failed to embed sub-chunks: %s", split_err)
                                            item_vec = [0.0] * 1024
                                            break
                                    else:
                                        item_vec = [0.0] * 1024
                                        break
                                else:
                                    logger.warning("Element embedding attempt %d/%d failed: %s", item_attempt, max_retries, item_exc)
                                    if item_attempt < max_retries:
                                        time.sleep(retry_delay * item_attempt)
                        if item_vec is None:
                            raise RuntimeError(f"Failed to embed chunk after {max_retries} attempts.") from item_err
                        result.append(item_vec)
                    return result
                
                logger.warning("Batch embedding attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)
        
        raise RuntimeError(f"All {max_retries} embedding attempts failed.") from last_exc

    def embed_query(self, text: str) -> List[float]:
        max_retries = 5
        retry_delay = 2.0
        
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                return super().embed_query(text)
            except Exception as e:
                last_exc = e
                if "NaN" in str(e) or "500" in str(e) or "Internal Server Error" in str(e):
                    logger.warning("Query embedding failed. Applying split-and-average NaN protection.")
                    words = text.split()
                    if len(words) > 1:
                        h1 = " ".join(words[:len(words)//2])
                        h2 = " ".join(words[len(words)//2:])
                        try:
                            r1 = super().embed_query(h1)
                            r2 = super().embed_query(h2)
                            avg = [(x + y) / 2.0 for x, y in zip(r1, r2)]
                            norm = math.sqrt(sum(x * x for x in avg))
                            if norm > 0:
                                return [x / norm for x in avg]
                            return avg
                        except Exception:
                            pass
                    return [0.0] * 1024
                
                logger.warning("Query embedding attempt %d/%d failed: %s", attempt, max_retries, e)
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)
        
        raise RuntimeError(f"All {max_retries} query embedding attempts failed.") from last_exc


def get_embeddings() -> OllamaEmbeddings:
    """Return a configured OllamaEmbeddings instance for the active embedding model."""
    return NaNSafeOllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)


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
