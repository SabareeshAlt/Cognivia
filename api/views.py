"""
Django REST API for RAG System
Implements streaming responses with optimized performance
"""

import json
import logging
import os
import sys

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import optimized RAG module
from optimized_rag import stream_optimized_response, get_optimized_response

logger = logging.getLogger(__name__)


def generate_streaming_response(question):
    """
    Optimized generator function for streaming LLM responses.
    Uses singleton instances and caching for 3-5x faster performance.
    """
    try:
        for chunk in stream_optimized_response(question):
            yield chunk
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"\n\n⚠️ Error: {str(e)}"


@csrf_exempt
@require_http_methods(["POST"])
def ask_question(request):
    """Handle questions from the frontend with optional streaming"""
    try:
        data = json.loads(request.body)
        question = data.get('question', '')
        stream = data.get('stream', False)  # Check if streaming is requested

        if not question:
            return JsonResponse({
                'error': 'No question provided'
            }, status=400)

        if stream:
            # Return streaming response
            response = StreamingHttpResponse(
                generate_streaming_response(question),
                content_type='text/plain'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
        else:
            # Return regular JSON response (non-streaming) using optimized module
            try:
                answer = get_optimized_response(question)
                return JsonResponse({
                    'answer': answer,
                    'status': 'success'
                })
            except Exception as e:
                error_msg = str(e)

                if "connection" in error_msg.lower() or "refused" in error_msg.lower() or "connect" in error_msg.lower():
                    return JsonResponse({
                        'answer': '⚠️ Ollama is not running. Please start Ollama with: ollama serve',
                        'status': 'error'
                    }, status=500)
                else:
                    return JsonResponse({
                        'answer': f'Error: {error_msg}',
                        'status': 'error'
                    }, status=500)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ask_question_stream(request):
    """Dedicated streaming endpoint"""
    try:
        data = json.loads(request.body)
        question = data.get('question', '')

        if not question:
            return JsonResponse({'error': 'No question provided'}, status=400)

        response = StreamingHttpResponse(
            generate_streaming_response(question),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        return response

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    """Health check endpoint"""
    health_status = {
        'django': True,
        'ollama': False,
        'vector_store': False
    }

    # Check Ollama
    try:
        import requests
        response = requests.get('http://localhost:11434/api/tags', timeout=2)
        if response.status_code == 200:
            health_status['ollama'] = True
    except:
        pass

    # Check Vector Store
    try:
        import os
        if os.path.exists('./milvus_local.db'):
            health_status['vector_store'] = True
    except:
        pass

    return JsonResponse({
        'status': 'healthy' if all(health_status.values()) else 'degraded',
        'services': health_status
    })


@csrf_exempt
@require_http_methods(["GET"])
def cache_info(request):
    """Get cache statistics"""
    try:
        from optimized_rag import get_cache_info
        cache_stats = get_cache_info()
        return JsonResponse({
            'hits': cache_stats.hits,
            'misses': cache_stats.misses,
            'maxsize': cache_stats.maxsize,
            'currsize': cache_stats.currsize,
            'hit_rate': f"{(cache_stats.hits / (cache_stats.hits + cache_stats.misses) * 100):.1f}%" if (cache_stats.hits + cache_stats.misses) > 0 else "N/A"
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def clear_cache(request):
    """Clear the document retrieval cache"""
    try:
        from optimized_rag import clear_cache
        clear_cache()
        return JsonResponse({'status': 'success', 'message': 'Cache cleared'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)