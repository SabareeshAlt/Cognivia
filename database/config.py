"""
database/config.py
------------------
Central configuration for the Cognivia database package.
All environment variables, constants, and project-path helpers live here.
Every other database/ module imports from this module — never from each other
for config — to avoid circular imports.
"""

import os
import socket
import threading
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _required_env(name: str, legacy_name: str | None = None) -> str:
    value = os.getenv(name)
    if value is not None and value.strip():
        return value.strip()
    if legacy_name:
        legacy_val = os.getenv(legacy_name)
        if legacy_val is not None and legacy_val.strip():
            return legacy_val.strip()
    raise RuntimeError(f"Environment variable '{name}' is required")


def _env_int(name: str, default: int, legacy_name: str | None = None) -> int:
    value = os.getenv(name)
    if value is not None and value.strip():
        return int(value.strip())
    if legacy_name:
        legacy_val = os.getenv(legacy_name)
        if legacy_val is not None and legacy_val.strip():
            return int(legacy_val.strip())
    return default


def _env_float(name: str, default: float, legacy_name: str | None = None) -> float:
    value = os.getenv(name)
    if value is not None and value.strip():
        return float(value.strip())
    if legacy_name:
        legacy_val = os.getenv(legacy_name)
        if legacy_val is not None and legacy_val.strip():
            return float(legacy_val.strip())
    return default


def _env_bool(name: str, default: bool = False, legacy_name: str | None = None) -> bool:
    value = os.getenv(name)
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if legacy_name:
        legacy_val = os.getenv(legacy_name)
        if legacy_val is not None:
            return legacy_val.strip().lower() in {"1", "true", "yes", "on"}
    return default


def _env_str(name: str, default: str = "", legacy_name: str | None = None) -> str:
    value = os.getenv(name)
    if value is not None and value.strip():
        return value.strip()
    if legacy_name:
        legacy_val = os.getenv(legacy_name)
        if legacy_val is not None and legacy_val.strip():
            return legacy_val.strip()
    return default


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or "your-cluster-id" in normalized
        or "your_zilliz_api_key_here" in normalized
    )

# ---------------------------------------------------------------------------
# RAG constants
# ---------------------------------------------------------------------------

INSUFFICIENT_CONTEXT_MESSAGE = "Not found in the provided documents."

STOPWORDS = {
    "a", "an", "and", "are", "for", "from", "in", "is", "of", "on", "or",
    "the", "to", "what", "which", "with", "each", "tell", "me",
}

# Syllabus section headings that contain noise (references, lab requirements, etc.)
_SYLLABUS_NOISE_HEADINGS = (
    "text books", "textbooks", "references", "reference books",
    "lab requirements", "hardware requirements", "software requirements",
    "list of experiments", "co-curricular activities", "beyond the syllabus",
    "online resources", "web resources", "assessment methodology",
    "course outcomes", "program outcomes",
)

BM25_K1 = 1.5
BM25_B = 0.75

# ---------------------------------------------------------------------------
# Model / Retrieval config (env-driven)
# ---------------------------------------------------------------------------

COLLECTION_NAME = _env_str("COLLECTION_NAME", "cognivia")
EMBEDDING_MODEL = _env_str("EMBEDDING_MODEL", "bge-m3:latest")
LLM_MODEL = _env_str("COGNIVIA_LLM_MODEL", default="gemma4:latest", legacy_name="ACADEMERAG_LLM_MODEL")
OLLAMA_BASE_URL = _env_str("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_TEMPERATURE = _env_float("COGNIVIA_LLM_TEMPERATURE", default=0.1, legacy_name="ACADEMERAG_LLM_TEMPERATURE")
LLM_PROVIDER = "ollama"

TOP_K = _env_int("COGNIVIA_TOP_K", default=3, legacy_name="ACADEMERAG_TOP_K")
DYNAMIC_TOP_K_MIN = _env_int("COGNIVIA_TOP_K_MIN", default=2, legacy_name="ACADEMERAG_TOP_K_MIN")
DYNAMIC_TOP_K_MAX = _env_int("COGNIVIA_TOP_K_MAX", default=6, legacy_name="ACADEMERAG_TOP_K_MAX")
RELEVANCE_SCORE_THRESHOLD = _env_float("COGNIVIA_SCORE_THRESHOLD", default=0.35, legacy_name="ACADEMERAG_SCORE_THRESHOLD")

CHUNK_SIZE = _env_int("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 200)

MILVUS_TIMEOUT_SECONDS = _env_float("COGNIVIA_MILVUS_TIMEOUT_SECONDS", default=15.0, legacy_name="ACADEMERAG_MILVUS_TIMEOUT_SECONDS")
MILVUS_INIT_TIMEOUT_SECONDS = _env_float("COGNIVIA_MILVUS_INIT_TIMEOUT_SECONDS", default=10.0, legacy_name="ACADEMERAG_MILVUS_INIT_TIMEOUT_SECONDS")
MILVUS_HEALTHCHECK_TIMEOUT_SECONDS = _env_float("COGNIVIA_MILVUS_HEALTHCHECK_TIMEOUT_SECONDS", default=1.5, legacy_name="ACADEMERAG_MILVUS_HEALTHCHECK_TIMEOUT_SECONDS")
MILVUS_CIRCUIT_BREAKER_SECONDS = _env_float("COGNIVIA_MILVUS_CIRCUIT_BREAKER_SECONDS", default=60.0, legacy_name="ACADEMERAG_MILVUS_CIRCUIT_BREAKER_SECONDS")

INGEST_BATCH_SIZE = _env_int("COGNIVIA_INGEST_BATCH_SIZE", default=16, legacy_name="ACADEMERAG_INGEST_BATCH_SIZE")
INGEST_MAX_SECONDS = _env_float("COGNIVIA_INGEST_MAX_SECONDS", default=1800.0, legacy_name="ACADEMERAG_INGEST_MAX_SECONDS")

# ---------------------------------------------------------------------------
# Milvus connection config factories
# ---------------------------------------------------------------------------

def _get_milvus_config() -> dict:
    milvus_uri = _env_str("COGNIVIA_MILVUS_URI", default="http://milvus:19530", legacy_name="ACADEMERAG_MILVUS_URI")
    milvus_token = _env_str("COGNIVIA_MILVUS_TOKEN", default="", legacy_name="ACADEMERAG_MILVUS_TOKEN")
    import logging
    logging.getLogger(__name__).info(
        "Using Milvus vector store at %s", milvus_uri
    )
    return {
        "uri": milvus_uri,
        "token": milvus_token,
        "collection": COLLECTION_NAME,
        "model": EMBEDDING_MODEL,
    }


def _get_deployment_mode() -> str:
    mode = os.getenv("COGNIVIA_MILVUS_DEPLOYMENT") or os.getenv("ACADEMERAG_MILVUS_DEPLOYMENT")
    if mode:
        return mode.strip().lower()
    if _env_bool("COGNIVIA_ENABLE_MILVUS_CLOUD", default=False, legacy_name="ACADEMERAG_ENABLE_MILVUS_CLOUD"):
        return "cloud"
    uri = os.getenv("COGNIVIA_MILVUS_URI") or os.getenv("ACADEMERAG_MILVUS_URI", "")
    if uri.startswith(("http://", "https://", "tcp://")):
        return "cloud"
    return "local"


def _get_cloud_config() -> dict | None:
    if _get_deployment_mode() == "cloud":
        return _get_milvus_config()
    return None


def _get_local_config() -> dict:
    return {
        "uri": os.path.join(PROJECT_ROOT, "milvus_local.db"),
        "token": "",
        "collection": COLLECTION_NAME,
        "model": EMBEDDING_MODEL,
    }


def _chunk_profile() -> str:
    return f"size={CHUNK_SIZE};overlap={CHUNK_OVERLAP};embed={EMBEDDING_MODEL}"


# ---------------------------------------------------------------------------
# Connectivity probing (socket-level, TTL-cached)
# ---------------------------------------------------------------------------

_connectivity_cache: dict = {
    "reachable": None,
    "checked_at": 0.0,
}
_connectivity_lock = threading.Lock()


def _milvus_endpoint_reachable(
    cfg: dict, ttl_seconds: float = 60.0, force_check: bool = False
) -> bool:
    """Return True if the Milvus URI is reachable via a TCP socket probe.

    Results are cached for `ttl_seconds`.  Local file-based URIs are always
    considered reachable without a network probe.
    """
    import logging
    _log = logging.getLogger(__name__)

    uri = cfg.get("uri", "")
    if not uri:
        return False
    # File-based Milvus Lite URIs — always local
    if not (uri.startswith("http://") or uri.startswith("https://") or uri.startswith("tcp://")):
        return True

    now = time.monotonic()
    if not force_check:
        with _connectivity_lock:
            if (
                _connectivity_cache["reachable"] is not None
                and (now - _connectivity_cache["checked_at"]) < ttl_seconds
            ):
                return _connectivity_cache["reachable"]

    reachable = False
    try:
        parsed = urlparse(uri)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if hostname:
            socket.gethostbyname(hostname)  # DNS check
            with socket.create_connection((hostname, port), timeout=1.0):
                reachable = True
    except Exception as exc:
        _log.debug("Milvus endpoint unreachable (%s): %s", uri, exc)

    with _connectivity_lock:
        _connectivity_cache["reachable"] = reachable
        _connectivity_cache["checked_at"] = now
    return reachable


def _validate_milvus_connection(cfg: dict) -> bool:
    """Perform a live Milvus round-trip validation (has_collection probe)."""
    try:
        if not _milvus_endpoint_reachable(cfg, force_check=True):
            return False
        from pymilvus import MilvusClient  # local import to avoid circular
        client = MilvusClient(uri=cfg["uri"], token=cfg["token"], timeout=2.5)
        client.has_collection(cfg["collection"])
        return True
    except Exception:
        return False


def _get_active_milvus_mode() -> str:
    """Return the active Milvus mode string: AUTO | CLOUD | LOCAL."""
    return (os.getenv("COGNIVIA_MILVUS_MODE") or os.getenv("ACADEMERAG_MILVUS_MODE", "AUTO")).strip().upper()
