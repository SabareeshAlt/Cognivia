import json
import logging
import os
import sys
import time
import threading
import importlib
from django.conf import settings
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .auth_utils import jwt_required
from .rate_limit import ratelimit
from .responses import json_error
from .metrics import render_prometheus
from prometheus_client import Histogram

LLM_GENERATION_LATENCY = Histogram(
    "llm_generation_latency_seconds",
    "Latency of LLM generation in seconds"
)

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

logger = logging.getLogger(__name__)

_rag_modules_loaded = False
_stream_fn = None
_response_fn = None
_vector_store_fn = None
_diagnostics_fn = None
_rag_module_mtime = None
_vector_ready_cache = {
    "ready": False,
    "inflight": False,
    "last_check": 0.0,
    "last_error": None,
}
_vector_ready_lock = threading.Lock()


def _load_rag_modules():
    """Lazy-load RAG modules so Django startup doesn't crash."""
    global _rag_modules_loaded, _stream_fn, _response_fn, _vector_store_fn, _diagnostics_fn, _rag_module_mtime

    milvus_path = os.path.join(parent_dir, "database", "__init__.py")
    current_mtime = os.path.getmtime(milvus_path) if os.path.exists(milvus_path) else None
    if _rag_modules_loaded and _rag_module_mtime == current_mtime:
        return

    try:
        milvus_module = importlib.import_module("database")
        llm_module = importlib.import_module("rag.llm_orchestration")
        if _rag_modules_loaded and settings.DEBUG:
            milvus_module = importlib.reload(milvus_module)
            llm_module = importlib.reload(llm_module)

        _stream_fn = llm_module.stream_optimized_response
        _response_fn = llm_module.get_optimized_response
        _vector_store_fn = milvus_module.get_vector_store
        _diagnostics_fn = getattr(milvus_module, "get_retrieval_diagnostics", None)
        _rag_modules_loaded = True
        _rag_module_mtime = current_mtime
        logger.info("RAG modules loaded successfully")
    except Exception as exc:
        logger.error("Failed to load RAG modules: %s", exc)
        raise


def _classify_runtime_error(exc: Exception) -> tuple[str, int]:
    raw = str(exc)
    text = raw.lower()

    connection_refused_patterns = [
        "winerror 10061",
        "actively refused",
        "connection refused",
        "failed to establish a new connection",
        "[errno 111]",
    ]

    if any(pattern in text for pattern in connection_refused_patterns):
        return (
            "LLM dependency is unreachable. Start Ollama and ensure OLLAMA_BASE_URL is correct.",
            503,
        )

    if "all llm providers failed" in text or "all streaming llm providers failed" in text or ("ollama" in text and "failed" in text):
        return (
            "No available LLM provider. Verify Ollama configuration and try again.",
            503,
        )

    if "timed out" in text or "timeout" in text:
        return (
            "Upstream dependency timed out while processing your request. Please retry.",
            504,
        )

    return ("Failed to process the question due to an internal dependency error.", 500)


def generate_streaming_response(question):
    """Generator that yields data chunks for the frontend."""
    start_time = time.time()
    try:
        # Yield instantly to flush HTTP headers to frontend and prevent 10s streamOpenTimeout.
        yield f'data: {json.dumps({"type": "status", "content": "Waking up RAG engine..."})}\n\n'
        _load_rag_modules()
        for chunk in _stream_fn(question):
            if isinstance(chunk, str) and not chunk.startswith("data:"):
                yield f'data: {json.dumps({"type": "token", "content": chunk})}\n\n'
            else:
                yield chunk
        LLM_GENERATION_LATENCY.observe(time.time() - start_time)
    except Exception as exc:
        logger.error("Streaming error: %s", exc, exc_info=True)
        safe_message, _ = _classify_runtime_error(exc)
        yield f'data: {json.dumps({"type": "error", "content": safe_message})}\n\n'
        yield f'data: {json.dumps({"type": "done", "content": ""})}\n\n'


def _probe_vector_dependencies():
    try:
        _load_rag_modules()
        vector_store = _vector_store_fn()
        ready = bool(vector_store)
        error = None
    except Exception as exc:
        ready = False
        error = str(exc)

    with _vector_ready_lock:
        _vector_ready_cache["ready"] = ready
        _vector_ready_cache["last_error"] = error
        _vector_ready_cache["last_check"] = time.monotonic()
        _vector_ready_cache["inflight"] = False


def _refresh_vector_dependencies_async(min_interval_seconds: float = 10.0):
    with _vector_ready_lock:
        if _vector_ready_cache["inflight"]:
            return
        if (time.monotonic() - _vector_ready_cache["last_check"]) < min_interval_seconds:
            return
        _vector_ready_cache["inflight"] = True
    if "test" in sys.argv:
        _probe_vector_dependencies()
    else:
        threading.Thread(target=_probe_vector_dependencies, daemon=True).start()


import re

def detect_prompt_injection(text: str) -> bool:
    """Pre-flight scanner to detect jailbreak patterns."""
    text_lower = text.lower()
    patterns = [
        r"ignore (all )?(previous )?instructions",
        r"forget (all )?(previous )?instructions",
        r"bypass (all )?(previous )?instructions",
        r"system prompt",
        r"jailbreak",
        r"developer mode",
        r"do anything now",
        r"dan mode",
        r"you are now",
        r"act as",
        r"pretend to be",
        r"forget everything",
        r"override (all )?(previous )?instructions",
        r"</user_question>",
        r"<context>",
        r"```",
        r"base64",
    ]
    for pattern in patterns:
        if re.search(pattern, text_lower):
            return True
    return False



@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@ratelimit(key="ip", rate=getattr(settings, "RATELIMIT_DEFAULT", "30/m"), block=True)
def ask_question(request):
    """Handles both /api/ask/ and /api/ask/stream/."""
    try:
        data = json.loads(request.body)
        question = data.get("question", "")
        request_id = getattr(request, "request_id", "-")
        wants_stream = data.get("stream", False) or request.path.endswith("/stream/")

        if not question:
            return json_error(request, "No question provided", 400)
        if len(question) > settings.MAX_QUESTION_LENGTH:
            return JsonResponse(
                {
                    "error": f"Question too long. Max length is {settings.MAX_QUESTION_LENGTH} characters.",
                    "success": False,
                    "trace_id": request_id,
                },
                status=400,
            )


        if detect_prompt_injection(question):
            return JsonResponse(
                {
                    "error": "Potentially unsafe input detected.",
                    "success": False,
                    "trace_id": request_id,
                },
                status=400,
            )

        try:
            _load_rag_modules()
        except Exception as exc:
            logger.error("RAG module load failed: %s", exc, exc_info=True)
            return JsonResponse(
                {
                    "error": "RAG backend initialization failed.",
                    "details": "Internal server configuration error",
                    "success": False,
                    "trace_id": request_id,
                },
                status=500,
            )

        if wants_stream:
            response = StreamingHttpResponse(
                generate_streaming_response(question),
                content_type="text/event-stream",
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response

        try:
            start_time = time.time()
            res = _response_fn(question, return_score=True)
            if isinstance(res, tuple) and len(res) == 2:
                answer, score_payload = res
            else:
                answer = res
                score_payload = {
                    "final_rag_score": 100.0,
                    "confidence_label": "High",
                    "retrieval_relevance_score": 100.0,
                    "context_coverage_score": 100.0,
                    "answer_grounding_score": 100.0,
                    "citation_confidence_score": 100.0
                }
            LLM_GENERATION_LATENCY.observe(time.time() - start_time)
        except Exception as exc:
            logger.error("Question processing failed: %s", exc, exc_info=True)
            safe_message, status_code = _classify_runtime_error(exc)
            return json_error(request, safe_message, status_code)

        return JsonResponse({
            "answer": answer,
            "status": "success",
            "success": True,
            "trace_id": request_id,
            "rag_score": score_payload["final_rag_score"],
            "rag_confidence": score_payload["confidence_label"],
            "metrics": score_payload
        })

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return json_error(request, "Invalid JSON in request body", 400)
    except Exception as exc:
        logger.error("ask_question error: %s", exc, exc_info=True)
        safe_message, status_code = _classify_runtime_error(exc)
        return json_error(request, safe_message, status_code)


@require_http_methods(["GET"])
def health_live(request):
    """Liveness probe: Django is up and serving HTTP."""
    return JsonResponse({"status": "alive", "service": "academerag-api"})


@require_http_methods(["GET"])
@jwt_required
@ratelimit(key="ip", rate="60/m", block=True)
def health_ready(request):
    """Readiness probe with dependency checks."""
    started = time.monotonic()
    timeout_s = max(getattr(settings, "RAG_READY_TIMEOUT_MS", 5000), 1000) / 1000.0
    health_status = {
        "django": True,
        "llm": False,
        "llm_provider": "ollama",
        "ollama": False,
        "vector_store": False,
    }

    # Lazy-load RAG modules to determine active routing
    groq_active = False
    try:
        _load_rag_modules()
        from rag.llm_orchestration import _groq_usable
        groq_active = _groq_usable()
    except Exception as exc:
        logger.debug("Failed to check Groq usability during health probe: %s", exc)

    health_status["llm_provider"] = "groq" if groq_active else "ollama"

    try:
        import requests as http_requests
        ollama_url = getattr(settings, "OLLAMA_HEALTHCHECK_URL", "http://localhost:11434").rstrip("/") + "/"
        resp = http_requests.get(ollama_url, timeout=2)
        if resp.status_code == 200:
            health_status["ollama"] = True
    except Exception as exc:
        logger.debug("Ollama health probe failed: %s", exc)

    if groq_active:
        # If Groq is active (configured and online), the primary LLM pipeline is healthy
        health_status["llm"] = True
    else:
        health_status["llm"] = health_status["ollama"]

    elapsed = time.monotonic() - started
    if elapsed <= timeout_s:
        _refresh_vector_dependencies_async(min_interval_seconds=10.0)
        with _vector_ready_lock:
            cache_age = time.monotonic() - _vector_ready_cache["last_check"]
            cache_fresh = cache_age <= 60.0
            if _vector_ready_cache["ready"] and not _vector_ready_cache["last_error"]:
                health_status["vector_store"] = True
            elif cache_fresh and _vector_ready_cache["ready"]:
                health_status["vector_store"] = True
            elif _vector_ready_cache["last_error"]:
                logger.warning("Readiness check - vector store: %s", _vector_ready_cache["last_error"])
            elif not cache_fresh:
                logger.warning("Readiness check - vector store status is stale, waiting for refresh.")
    else:
        logger.warning("Readiness check timed out before vector dependency checks.")

    overall = "healthy" if health_status["django"] and health_status["llm"] and health_status["vector_store"] else "degraded"
    return JsonResponse({"status": overall, "services": health_status})


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/m", block=True)
def health_check(request):
    """Backward-compatible health alias mapped to readiness checks."""
    return health_ready(request)


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="120/m", block=True)
@jwt_required
def metrics(request):
    body = render_prometheus()
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")


@require_http_methods(["GET"])
@jwt_required
@ratelimit(key="ip", rate="30/m", block=True)
def retrieval_diagnostics(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_superuser", False):
        return json_error(request, "Admin access required", 403)
    try:
        _load_rag_modules()
        return JsonResponse(
            {
                "success": True,
                "trace_id": getattr(request, "request_id", "-"),
                "diagnostics": _diagnostics_fn(),
            }
        )
    except Exception as exc:
        return json_error(request, f"Diagnostics unavailable: {exc}", 500)
