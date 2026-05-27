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
        
        # Warmup is opt-in to keep tests/CI deterministic.
        if os.environ.get("RAG_WARMUP_ON_STARTUP", "false").lower() != "true":
            return

        # Avoid duplicate warmups under autoreloader parent process.
        if os.environ.get("RUN_MAIN") != "true":
            return

        def _warmup_active_stack():
            try:
                from Milvus import get_retriever, preload_cross_encoder

                logger.info("Starting RAG warmup...")
                get_retriever()
                preload_cross_encoder()
                logger.info("RAG warmup completed.")
            except Exception as exc:
                logger.warning("RAG warmup failed (will initialize lazily): %s", exc)

        threading.Thread(target=_warmup_active_stack, daemon=True).start()
