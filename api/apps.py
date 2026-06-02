from django.apps import AppConfig
import logging
import threading

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    
    def ready(self):
        """
        Called when Django starts up.
        Warm up active RAG components for faster first request.
        """
        import os
        import threading
        
        # Avoid duplicate warmups under autoreloader parent process.
        # But allow warmup when running with --noreload or not in DEBUG mode.
        from django.conf import settings
        import sys
        
        is_reloader_parent = (
            os.environ.get("RUN_MAIN") != "true" and 
            "runserver" in sys.argv and
            "--noreload" not in sys.argv
        )
        if is_reloader_parent:
            return

        # 1. ALWAYS initialize the BM25 index in a background thread to prevent cold starts
        def _init_bm25_bg():
            try:
                from database.bm25 import _init_bm25_index_at_startup
                logger.info("Initializing BM25 index in background thread...")
                _init_bm25_index_at_startup()
                logger.info("BM25 index initialization completed.")
            except Exception as e:
                logger.error("Failed to initialize BM25 index in background: %s", e)

        threading.Thread(target=_init_bm25_bg, daemon=True).start()

        # Warmup is opt-in to keep tests/CI deterministic.
        if os.environ.get("RAG_WARMUP_ON_STARTUP", "false").lower() != "true":
            return

        def _warmup_active_stack():
            try:
                from database import get_retriever, preload_cross_encoder, OLLAMA_BASE_URL, EMBEDDING_MODEL, LLM_MODEL
                import requests

                logger.info("Starting RAG warmup...")
                
                # 1. Warm up database, Milvus connections, and BM25 index
                get_retriever()
                
                # 2. Warm up CrossEncoder model
                preload_cross_encoder()
                
                # 3. Pre-load Ollama embedding model into memory
                try:
                    logger.info("Pre-loading Ollama embedding model: %s", EMBEDDING_MODEL)
                    requests.post(
                        f"{OLLAMA_BASE_URL.rstrip('/')}/api/embed",
                        json={"model": EMBEDDING_MODEL, "input": "warmup"},
                        timeout=15
                    )
                except Exception as e:
                    logger.warning("Ollama embedding model warmup failed: %s", e)

                # 4. Pre-load Ollama LLM model into memory
                try:
                    logger.info("Pre-loading Ollama LLM model: %s", LLM_MODEL)
                    requests.post(
                        f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate",
                        json={"model": LLM_MODEL, "prompt": "", "options": {"num_predict": 1}},
                        timeout=20
                    )
                except Exception as e:
                    logger.warning("Ollama LLM model warmup failed: %s", e)

                # 5. Populate vector readiness cache
                try:
                    logger.info("Populating initial vector readiness cache...")
                    from api.views import _probe_vector_dependencies
                    _probe_vector_dependencies()
                except Exception as e:
                    logger.warning("Failed to populate initial vector readiness cache: %s", e)

                logger.info("RAG warmup completed.")
            except Exception as exc:
                logger.warning("RAG warmup failed (will initialize lazily): %s", exc)

        threading.Thread(target=_warmup_active_stack, daemon=True).start()

