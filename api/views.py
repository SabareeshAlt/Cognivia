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

    milvus_path = os.path.join(parent_dir, "Milvus.py")
    current_mtime = os.path.getmtime(milvus_path) if os.path.exists(milvus_path) else None
    if _rag_modules_loaded and _rag_module_mtime == current_mtime:
        return

    try:
        milvus_module = importlib.import_module("Milvus")
        if _rag_modules_loaded:
            milvus_module = importlib.reload(milvus_module)

        _stream_fn = milvus_module.stream_optimized_response
        _response_fn = milvus_module.get_optimized_response
        _vector_store_fn = milvus_module.get_vector_store
        _diagnostics_fn = milvus_module.get_retrieval_diagnostics
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
            "LLM dependency is unreachable. Start Ollama and ensure OLLAMA_BASE_URL is correct, or configure GROQ cloud fallback.",
            503,
        )

    if "all llm providers failed" in text or "ollama" in text and "failed" in text:
        return (
            "No available LLM provider. Verify Ollama/Groq configuration and try again.",
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
    try:
        _load_rag_modules()
        for chunk in _stream_fn(question):
            yield chunk
    except Exception as exc:
        logger.error("Streaming error: %s", exc, exc_info=True)
        safe_message, _ = _classify_runtime_error(exc)
        yield f"\n\nError: {safe_message}"


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
    threading.Thread(target=_probe_vector_dependencies, daemon=True).start()


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

        try:
            _load_rag_modules()
        except Exception as exc:
            logger.error("RAG module load failed: %s", exc, exc_info=True)
            return JsonResponse(
                {
                    "error": "RAG backend initialization failed.",
                    "details": str(exc),
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
            answer = _response_fn(question)
        except Exception as exc:
            logger.error("Question processing failed: %s", exc, exc_info=True)
            safe_message, status_code = _classify_runtime_error(exc)
            return json_error(request, safe_message, status_code)

        return JsonResponse({"answer": answer, "status": "success", "success": True, "trace_id": request_id})

    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        return json_error(request, "Invalid JSON in request body", 400)
    except Exception as exc:
        logger.error("ask_question error: %s", exc, exc_info=True)
        safe_message, status_code = _classify_runtime_error(exc)
        return json_error(request, safe_message, status_code)


@require_http_methods(["GET"])
def health_live(request):
    """Liveness probe: process is up and serving HTTP."""
    return JsonResponse({"status": "alive", "service": "academerag-api"})


@require_http_methods(["GET"])
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
        "groq": False,
        "vector_store": False,
        "milvus_cloud": False,
    }

    provider = os.getenv("ACADEMERAG_LLM_PROVIDER", "ollama").strip().lower()
    use_groq = provider == "groq" or os.getenv("ACADEMERAG_USE_GROQ_CLOUD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    health_status["llm_provider"] = "groq" if use_groq else "ollama"

    try:
        import requests as http_requests

        ollama_url = getattr(settings, "OLLAMA_HEALTHCHECK_URL", "http://localhost:11434").rstrip("/") + "/"
        resp = http_requests.get(ollama_url, timeout=2)
        if resp.status_code == 200:
            health_status["ollama"] = True
    except Exception as exc:
        logger.debug("Ollama health probe failed: %s", exc)

    if use_groq:
        try:
            import requests as http_requests

            groq_base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
            groq_key = os.getenv("GROQ_API_KEY", "").strip()
            if groq_key:
                resp = http_requests.get(
                    f"{groq_base}/models",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    timeout=2,
                )
                if resp.status_code == 200:
                    health_status["groq"] = True
            else:
                logger.warning("Groq provider configured but GROQ_API_KEY is missing.")
        except Exception as exc:
            logger.debug("Groq health probe failed: %s", exc)

    health_status["llm"] = health_status["groq"] if use_groq else health_status["ollama"]
    if use_groq and not health_status["llm"]:
        health_status["llm"] = health_status["ollama"]

    elapsed = time.monotonic() - started
    if elapsed <= timeout_s:
        _refresh_vector_dependencies_async(min_interval_seconds=5.0)
        with _vector_ready_lock:
            cache_age = time.monotonic() - _vector_ready_cache["last_check"]
            cache_fresh = cache_age <= 15.0
            if cache_fresh and _vector_ready_cache["ready"]:
                health_status["vector_store"] = True
                health_status["milvus_cloud"] = True
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
def metrics(request):
    body = render_prometheus()
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")


@require_http_methods(["GET"])
@jwt_required
@ratelimit(key="ip", rate="30/m", block=True)
def retrieval_diagnostics(request):
    user = getattr(request, "user", None)
    if not user or not (user.is_staff or user.is_superuser):
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