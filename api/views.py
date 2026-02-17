import json
import logging
import sys
import os
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Path fix to find vector.py in root
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from vector import (
    stream_optimized_response, 
    get_optimized_response, 
    get_retriever
)

logger = logging.getLogger(__name__)

def generate_streaming_response(question):
    """Generator that yields data chunks for the frontend."""
    try:
        for chunk in stream_optimized_response(question):
            # We format as SSE (Server-Sent Events) for better frontend compatibility
            # or just raw text depending on your client. Let's stick to raw text for safety.
            yield chunk
    except Exception as e:
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
        
        # Check if user wants streaming (Explicit flag OR URL check)
        # If the URL ends in 'stream/', force streaming mode.
        wants_stream = data.get('stream', False) or request.path.endswith('/stream/')

        if not question:
            return JsonResponse({'error': 'No question provided'}, status=400)

        if wants_stream:
            response = StreamingHttpResponse(
                generate_streaming_response(question),
                content_type='text/event-stream'
            )
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response

        # Standard Response (Non-streaming)
        answer = get_optimized_response(question)
        return JsonResponse({'answer': answer, 'status': 'success'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def health_check(request):
    health_status = {'django': True, 'ollama': False, 'vector_store': False}
    
    # Check Ollama
    try:
        import requests
        if requests.get('http://localhost:11434/', timeout=1).status_code == 200:
            health_status['ollama'] = True
    except: pass
    
    # Check Vector Store
    try:
        if get_retriever():
            health_status['vector_store'] = True
    except: pass
    
    return JsonResponse({'status': 'healthy', 'services': health_status})