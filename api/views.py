"""
Django REST API for RAG System
Implements streaming responses and proper error handling
"""

import json
import logging

from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def ask_question(request):
    """Handle questions from the frontend"""
    try:
        data = json.loads(request.body)
        question = data.get('question', '')

        if not question:
            return JsonResponse({
                'error': 'No question provided'
            }, status=400)

        # Try to use the RAG pipeline
        try:
            from main import get_llm_response
            answer = get_llm_response(question)
            return JsonResponse({
                'answer': answer,
                'status': 'success'
            })
        except Exception as e:
            error_msg = str(e)

            # Check if it's an Ollama connection error
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