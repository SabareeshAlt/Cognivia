import time
import logging
import concurrent.futures
from typing import Optional, Set

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Assumed dependencies in Milvus.py:
# _get_cloud_config, _get_local_config, _search_milvus_with_config
# _cloud_circuit_breaker, CLOUD_FAILURE_THRESHOLD, CLOUD_COOLDOWN_SECONDS

def _search_cloud_milvus(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    logger.info("CLOUD_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    
    cfg = _get_cloud_config()
    if not cfg:
        logger.info("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Cloud not configured'", question)
        return []
    
    global _cloud_circuit_breaker
    if time.monotonic() < _cloud_circuit_breaker["bypass_until"]:
        logger.info("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Circuit breaker open'", question)
        return []

    timeout_sec = 5.0
    max_retries = 1
    
    for attempt in range(max_retries + 1):
        try:
            # Enforce strict Python-level timeout to ensure parallel BM25 execution is never blocked 
            # by a hung Milvus network call.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _search_milvus_with_config, 
                    cfg, question, k, target_sources, timeout_sec
                )
                # Give slightly more time than the Milvus timeout to allow clean internal timeout first
                docs = future.result(timeout=timeout_sec + 1.0) 
                
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info("CLOUD_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d | attempt=%d", 
                        question, latency_ms, len(docs), attempt + 1)
            _cloud_circuit_breaker["consecutive_failures"] = 0
            return docs
            
        except concurrent.futures.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("CLOUD_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f | attempt=%d", 
                           question, latency_ms, attempt + 1)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | attempt=%d | error='%s'", 
                           question, latency_ms, attempt + 1, exc)
            
        if attempt == max_retries:
            _cloud_circuit_breaker["consecutive_failures"] += 1
            if _cloud_circuit_breaker["consecutive_failures"] >= CLOUD_FAILURE_THRESHOLD:
                _cloud_circuit_breaker["bypass_until"] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
                logger.warning("Cloud Milvus circuit breaker OPENED for %.1fs", CLOUD_COOLDOWN_SECONDS)
            return []
            
        time.sleep(0.5)

    return []


def _search_local_milvus(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    logger.info("LOCAL_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    
    cfg = _get_local_config()
    timeout_sec = 3.0
    max_retries = 1
    
    for attempt in range(max_retries + 1):
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _search_milvus_with_config, 
                    cfg, question, k, target_sources, timeout_sec
                )
                docs = future.result(timeout=timeout_sec + 1.0)
                
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info("LOCAL_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d | attempt=%d", 
                        question, latency_ms, len(docs), attempt + 1)
            return docs
            
        except concurrent.futures.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("LOCAL_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f | attempt=%d", 
                           question, latency_ms, attempt + 1)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning("LOCAL_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | attempt=%d | error='%s'", 
                           question, latency_ms, attempt + 1, exc)
                           
        if attempt == max_retries:
            return []
            
        time.sleep(0.2)

    return []
