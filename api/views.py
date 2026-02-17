import json
import logging
import sys
import os
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Path fix to find Milvus.py in root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

logger = logging.getLogger(__name__)

# Lazy imports to avoid crashing Django startup if Milvus/Ollama is not ready
_rag_modules_loaded = False
_stream_fn = None
_response_fn = None
_retriever_fn = None


def _load_rag_modules():
    """Lazy-load RAG modules so Django startup doesn't crash."""
    global _rag_modules_loaded, _stream_fn, _response_fn, _retriever_fn
    if _rag_modules_loaded:
        return

    try:
        from Milvus import stream_optimized_response, get_optimized_response, get_retriever
        _stream_fn = stream_optimized_response
        _response_fn = get_optimized_response
        _retriever_fn = get_retriever
        _rag_modules_loaded = True
        logger.info("✅ RAG modules loaded successfully")
    except Exception as e:
        logger.error(f"❌ Failed to load RAG modules: {e}")
        raise

def generate_streaming_response(question):
    """Generator that yields data chunks for the frontend."""
    try:
        _load_rag_modules()
        for chunk in _stream_fn(question):
            yield chunk
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"\n\n⚠️ Error: {str(e)}"

@csrf_exempt
@require_http_methods(["POST"])
def ask_question(request):
    """
    Handles both /api/ask/ and /api/ask/stream/
    """
    try:
        data = json.loads(request.body)
        question = data.get('question', '')
        
        # Check if user wants streaming
        wants_stream = data.get('stream', False) or request.path.endswith('/stream/')

        if not question:
            return JsonResponse({'error': 'No question provided'}, status=400)

        # Ensure RAG modules are loaded
        try:
            _load_rag_modules()
        except Exception as e:
            logger.error(f"RAG module load failed: {e}")
            return JsonResponse({
                'error': f'RAG backend initialization failed: {str(e)}',
                'success': False
            }, status=500)

        if wants_stream:
            response = StreamingHttpResponse(
                generate_streaming_response(question),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        # Standard Response (Non-streaming)
        answer = _response_fn(question)
        return JsonResponse({'answer': answer, 'status': 'success', 'success': True})

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return JsonResponse({'error': 'Invalid JSON in request body', 'success': False}, status=400)
    except Exception as e:
        logger.error(f"ask_question error: {e}", exc_info=True)
        return JsonResponse({'error': str(e), 'success': False}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Health check — reports status of each service dependency."""
    health_status = {'django': True, 'ollama': False, 'vector_store': False, 'milvus_cloud': False}
    
    # Check Ollama
    try:
        import requests as http_requests
        resp = http_requests.get('http://localhost:11434/', timeout=2)
        if resp.status_code == 200:
            health_status['ollama'] = True
    except Exception:
        pass
    
    # Check Milvus Cloud / Vector Store
    try:
        _load_rag_modules()
        retriever = _retriever_fn()
        if retriever:
            health_status['vector_store'] = True
            health_status['milvus_cloud'] = True
    except Exception as e:
        logger.warning(f"Health check - vector store: {e}")
    
    overall = 'healthy' if all(health_status.values()) else 'degraded'
    return JsonResponse({'status': overall, 'services': health_status})