from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    
    def ready(self):
        """
        Called when Django starts up.
        Warm up RAG components for faster first request.
        """
        import os
        import sys
        
        # Only run warmup in main process (not during migrations, etc.)
        if os.environ.get('RUN_MAIN') == 'true' or 'runserver' not in sys.argv:
            try:
                # Add project root to path
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if project_root not in sys.path:
                    sys.path.insert(0, project_root)
                
                from optimized_rag import warmup
                logger.info("Starting RAG warmup...")
                warmup()
                logger.info("✅ RAG components ready - optimized for fast responses")
            except Exception as e:
                logger.warning(f"RAG warmup failed (will initialize on first request): {e}")
