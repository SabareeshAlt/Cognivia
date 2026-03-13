import hashlib
import logging
import math
import os
import re
import socket
import threading
import time
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from collections import Counter
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_milvus import Milvus
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient
from pypdf import PdfReader

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - handled at runtime when groq is selected
    ChatOpenAI = None

os.environ["MILVUS_ASYNC"] = "0"

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

INSUFFICIENT_CONTEXT_MESSAGE = (
    "I am not trained on this data source or the uploaded documents do not contain this information."
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "with",
    "each",
    "tell",
    "me",
}
BM25_K1 = 1.5
BM25_B = 0.75


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable '{name}' is required")
    return value.strip()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or "your-cluster-id" in normalized
        or "your_zilliz_api_key_here" in normalized
    )


COLLECTION_NAME = _required_env("COLLECTION_NAME")
EMBEDDING_MODEL = _required_env("EMBEDDING_MODEL")
LLM_MODEL = _required_env("ACADEMERAG_LLM_MODEL")
OLLAMA_BASE_URL = _required_env("OLLAMA_BASE_URL")
LLM_TEMPERATURE = _env_float("ACADEMERAG_LLM_TEMPERATURE", 0.7)
LLM_PROVIDER = _env_str("ACADEMERAG_LLM_PROVIDER", "ollama").lower()
GROQ_API_KEY = _env_str("GROQ_API_KEY")
GROQ_BASE_URL = _env_str("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = _env_str("ACADEMERAG_GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_REQUEST_TIMEOUT_SECONDS = _env_float("ACADEMERAG_GROQ_TIMEOUT_SECONDS", 15.0)
TOP_K = _env_int("ACADEMERAG_TOP_K", 3)
DYNAMIC_TOP_K_MIN = _env_int("ACADEMERAG_TOP_K_MIN", 2)
DYNAMIC_TOP_K_MAX = _env_int("ACADEMERAG_TOP_K_MAX", 6)
RELEVANCE_SCORE_THRESHOLD = _env_float("ACADEMERAG_SCORE_THRESHOLD", 0.35)
CHUNK_SIZE = _env_int("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 200)
MILVUS_TIMEOUT_SECONDS = _env_float("ACADEMERAG_MILVUS_TIMEOUT_SECONDS", 15.0)
MILVUS_INIT_TIMEOUT_SECONDS = _env_float("ACADEMERAG_MILVUS_INIT_TIMEOUT_SECONDS", 10.0)
MILVUS_HEALTHCHECK_TIMEOUT_SECONDS = _env_float("ACADEMERAG_MILVUS_HEALTHCHECK_TIMEOUT_SECONDS", 1.5)
MILVUS_CIRCUIT_BREAKER_SECONDS = _env_float("ACADEMERAG_MILVUS_CIRCUIT_BREAKER_SECONDS", 60.0)
INGEST_BATCH_SIZE = _env_int("ACADEMERAG_INGEST_BATCH_SIZE", 16)
INGEST_MAX_SECONDS = _env_float("ACADEMERAG_INGEST_MAX_SECONDS", 1800.0)

_vector_store_cache = None
_vector_store_lock = threading.Lock()
_milvus_health = {
    "unhealthy_until": 0.0,
    "last_error": None,
}
_background_sync_state = {
    "inflight": False,
}
_background_sync_lock = threading.Lock()
_fallback_cache_lock = threading.Lock()
_fallback_cache_state = {
    "corpus": tuple(),
    "stats": None,
    "signature": None,
    "inflight": False,
}


def _chunk_profile() -> str:
    return f"size={CHUNK_SIZE};overlap={CHUNK_OVERLAP};embed={EMBEDDING_MODEL}"


def _compute_dynamic_top_k(question: str) -> int:
    # Scale retrieval depth with question complexity while staying bounded.
    qlen = len((question or "").strip())
    if qlen <= 80:
        k = TOP_K
    elif qlen <= 220:
        k = TOP_K + 1
    else:
        k = TOP_K + 2
    return max(DYNAMIC_TOP_K_MIN, min(DYNAMIC_TOP_K_MAX, k))


def _get_tracking_model():
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rag_project.settings")
        import django
        from django.apps import apps

        if not apps.ready:
            django.setup()
        from api.models import IndexedDocument

        return IndexedDocument
    except Exception as exc:
        logger.debug("Index tracking model unavailable: %s", exc)
        return None


def _load_tracking_map() -> dict[str, str]:
    model = _get_tracking_model()
    if model is None:
        return {}
    rows = model.objects.filter(
        embedding_model=EMBEDDING_MODEL,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    ).only("document_path", "content_hash")
    return {row.document_path: row.content_hash for row in rows}


def _save_tracking_rows(file_metadata: list[dict]) -> None:
    model = _get_tracking_model()
    if model is None:
        return
    for item in file_metadata:
        model.objects.update_or_create(
            document_path=item["relative_path"],
            defaults={
                "source_name": item["source"],
                "content_hash": item["content_hash"],
                "embedding_model": EMBEDDING_MODEL,
                "chunk_size": CHUNK_SIZE,
                "chunk_overlap": CHUNK_OVERLAP,
                "chunk_profile": _chunk_profile(),
            },
        )
    valid_paths = [item["relative_path"] for item in file_metadata]
    model.objects.exclude(document_path__in=valid_paths).delete()


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def get_pdf_files() -> list[str]:
    pdf_files = []
    if os.path.exists(DOCUMENTS_DIR):
        for filename in sorted(os.listdir(DOCUMENTS_DIR)):
            if filename.lower().endswith(".pdf"):
                pdf_files.append(os.path.join(DOCUMENTS_DIR, filename))
    for filename in ["RAG sample 1.pdf", "RAG sample 2.pdf", "RAG sample 3.pdf"]:
        root_path = os.path.join(PROJECT_ROOT, filename)
        if os.path.exists(root_path):
            pdf_files.append(root_path)
    by_name = {}
    for path in pdf_files:
        name = os.path.basename(path).lower()
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = path
            continue
        # Prefer managed documents/ copies over root duplicates.
        if os.path.commonpath([DOCUMENTS_DIR, path]) == DOCUMENTS_DIR:
            by_name[name] = path
    return sorted(by_name.values())


def _collect_pdf_metadata() -> list[dict]:
    items = []
    for pdf_path in get_pdf_files():
        rel_path = os.path.relpath(pdf_path, PROJECT_ROOT)
        items.append(
            {
                "path": pdf_path,
                "relative_path": rel_path,
                "source": os.path.basename(pdf_path),
                "content_hash": _file_sha256(pdf_path),
            }
        )
    return items


def compute_sync_decision(
    file_metadata: list[dict], tracked_hashes: dict[str, str], force_reindex: bool
) -> tuple[bool, str]:
    if force_reindex:
        return True, "forced"
    if not file_metadata:
        return False, "no-documents"
    if not tracked_hashes:
        return True, "no-tracking-state"

    current_paths = {item["relative_path"] for item in file_metadata}
    tracked_paths = set(tracked_hashes.keys())
    if current_paths != tracked_paths:
        return True, "document-set-changed"

    for item in file_metadata:
        if tracked_hashes.get(item["relative_path"]) != item["content_hash"]:
            return True, f"content-changed:{item['relative_path']}"
    return False, "unchanged"


def compute_rebuild_state(force_reindex: bool = False) -> tuple[bool, str]:
    file_metadata = _collect_pdf_metadata()
    tracked_hashes = _load_tracking_map()
    return compute_sync_decision(file_metadata, tracked_hashes, force_reindex)


def _load_and_chunk_files(file_metadata: list[dict]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    all_chunks = []
    logger.info("Starting PDF parse/chunk stage for %s file(s).", len(file_metadata))
    for item in file_metadata:
        file_start = time.monotonic()
        logger.info("Parsing file: %s", item["relative_path"])
        reader = PdfReader(item["path"])
        page_count = len(reader.pages)
        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks = splitter.split_text(page_text)
                for chunk_idx, chunk in enumerate(chunks):
                    all_chunks.append(
                        Document(
                            page_content=chunk,
                            metadata={
                                "source": item["source"],
                                "document_path": item["relative_path"],
                                "document_hash": item["content_hash"],
                                "page_number": idx,
                                "chunk_index": chunk_idx,
                            },
                        )
                    )
            if idx % 10 == 0 or idx == page_count:
                logger.info("  %s page(s) processed for %s", idx, item["source"])
        file_chunks = [doc for doc in all_chunks if doc.metadata["document_path"] == item["relative_path"]]
        if not file_chunks:
            logger.warning("Skipping %s because no text was extracted.", item["source"])
            continue
        logger.info(
            "Chunked %s into %s chunk(s) in %.1fs",
            item["source"],
            len(file_chunks),
            time.monotonic() - file_start,
        )
    logger.info("Completed parse/chunk stage. Total chunks: %s", len(all_chunks))
    return all_chunks


def _ingest_documents_in_batches(vector_store: Milvus, docs: list[Document]) -> None:
    total = len(docs)
    start = time.monotonic()
    logger.info(
        "Starting Milvus ingestion for %s chunk(s) with batch size %s (timeout %.0fs).",
        total,
        INGEST_BATCH_SIZE,
        INGEST_MAX_SECONDS,
    )
    for offset in range(0, total, INGEST_BATCH_SIZE):
        elapsed = time.monotonic() - start
        if elapsed > INGEST_MAX_SECONDS:
            raise TimeoutError(
                f"Ingestion timed out after {elapsed:.1f}s (limit {INGEST_MAX_SECONDS:.1f}s)"
            )
        batch = docs[offset : offset + INGEST_BATCH_SIZE]
        batch_start = time.monotonic()
        vector_store.add_documents(batch)
        completed = min(offset + len(batch), total)
        percent = (completed / total) * 100.0
        batch_elapsed = time.monotonic() - batch_start
        avg_per_chunk = (time.monotonic() - start) / completed
        remaining_chunks = total - completed
        eta = remaining_chunks * avg_per_chunk
        logger.info(
            "Ingestion progress: %s/%s chunks (%.1f%%) | batch %.2fs | elapsed %.1fs | eta %.1fs",
            completed,
            total,
            percent,
            batch_elapsed,
            time.monotonic() - start,
            eta,
        )
    logger.info("Milvus ingestion completed in %.1fs.", time.monotonic() - start)


def _get_milvus_config():
    if not _env_bool("ACADEMERAG_ENABLE_MILVUS_CLOUD", default=False):
        logger.info("Milvus Cloud disabled by ACADEMERAG_ENABLE_MILVUS_CLOUD=false")
        return None
    milvus_uri = _required_env("ACADEMERAG_MILVUS_URI")
    milvus_token = _required_env("ACADEMERAG_MILVUS_TOKEN")
    if _looks_like_placeholder(milvus_uri) or _looks_like_placeholder(milvus_token):
        logger.warning("Milvus Cloud configured with placeholder credentials.")
        return None
    if not milvus_uri.startswith("https://"):
        raise ValueError("ACADEMERAG_MILVUS_URI must be a https:// URL")
    return {
        "uri": milvus_uri,
        "token": milvus_token,
        "collection": COLLECTION_NAME,
        "model": EMBEDDING_MODEL,
    }


def _connect_milvus_client(cfg: dict) -> MilvusClient:
    return MilvusClient(
        uri=cfg["uri"],
        token=cfg["token"],
        timeout=MILVUS_TIMEOUT_SECONDS,
    )


def _connect_milvus_client_with_timeout(cfg: dict, timeout_seconds: float) -> MilvusClient:
    return MilvusClient(
        uri=cfg["uri"],
        token=cfg["token"],
        timeout=timeout_seconds,
    )


def _mark_milvus_unhealthy(error: str) -> None:
    _milvus_health["last_error"] = error
    _milvus_health["unhealthy_until"] = time.monotonic() + MILVUS_CIRCUIT_BREAKER_SECONDS


def _milvus_circuit_open() -> bool:
    return time.monotonic() < _milvus_health["unhealthy_until"]


def _milvus_endpoint_reachable(cfg: dict) -> bool:
    if _milvus_circuit_open():
        return False
    try:
        parsed = urlparse(cfg["uri"])
        host = parsed.hostname
        port = parsed.port or 443
        if not host:
            raise ValueError("Milvus URI missing hostname")
        with socket.create_connection((host, port), timeout=MILVUS_HEALTHCHECK_TIMEOUT_SECONDS):
            pass
        return True
    except Exception as exc:
        _mark_milvus_unhealthy(str(exc))
        logger.warning("Milvus endpoint health check failed fast: %s", exc)
        return False


def collection_exists(cfg: dict) -> bool:
    return _connect_milvus_client(cfg).has_collection(cfg["collection"])


def _get_embedding_dimension(embeddings: OllamaEmbeddings) -> int:
    return len(embeddings.embed_query("dimension probe"))


def ensure_collection_schema(cfg: dict, embeddings: OllamaEmbeddings, recreate: bool = False) -> bool:
    """Ensure collection exists with explicit schema before ingestion."""
    client = _connect_milvus_client(cfg)
    exists = client.has_collection(cfg["collection"])

    if exists and recreate:
        logger.info("Dropping existing Milvus collection: %s", cfg["collection"])
        client.drop_collection(cfg["collection"])
        _wait_for_collection_absence(client, cfg["collection"])
        exists = False

    if exists:
        return True

    dim = _get_embedding_dimension(embeddings)
    logger.info("Creating Milvus collection '%s' with vector dim=%s", cfg["collection"], dim)

    fields = [
        FieldSchema(name="pk", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=dim),
    ]
    schema = CollectionSchema(
        fields=fields,
        description="AcademeRAG document chunks",
        enable_dynamic_field=True,
    )
    index_params = MilvusClient.prepare_index_params()
    index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(
        collection_name=cfg["collection"],
        schema=schema,
        index_params=index_params,
        auto_id=True,
    )
    _wait_for_collection_presence(client, cfg["collection"])
    return True


def _wait_for_collection_presence(client: MilvusClient, collection_name: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if client.has_collection(collection_name):
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for collection '{collection_name}' to become available")


def _wait_for_collection_absence(client: MilvusClient, collection_name: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if not client.has_collection(collection_name):
                return
        except Exception:
            return
        time.sleep(0.2)
    raise TimeoutError(f"Timed out waiting for collection '{collection_name}' to be dropped")


def _milvus_cloud_ready() -> bool:
    return _get_milvus_config() is not None


def _build_fallback_stats_from_docs(docs: tuple[Document, ...]) -> dict:
    tokenized_docs: list[list[str]] = []
    term_frequencies: list[Counter] = []
    document_frequencies: Counter = Counter()
    total_length = 0

    for doc in docs:
        tokens = _tokenize(doc.page_content)
        tokenized_docs.append(tokens)
        tf = Counter(tokens)
        term_frequencies.append(tf)
        total_length += len(tokens)
        for token in tf:
            document_frequencies[token] += 1

    avg_doc_length = (total_length / len(docs)) if docs else 0.0
    return {
        "corpus": docs,
        "tokenized_docs": tokenized_docs,
        "term_frequencies": term_frequencies,
        "document_frequencies": document_frequencies,
        "avg_doc_length": avg_doc_length,
        "doc_count": len(docs),
    }


def _fallback_signature(file_metadata: list[dict]) -> tuple[tuple[str, str], ...]:
    return tuple((item["relative_path"], item["content_hash"]) for item in file_metadata)


def _refresh_fallback_cache() -> None:
    file_metadata = _collect_pdf_metadata()
    docs = tuple(_load_and_chunk_files(file_metadata))
    stats = _build_fallback_stats_from_docs(docs)
    with _fallback_cache_lock:
        _fallback_cache_state["corpus"] = docs
        _fallback_cache_state["stats"] = stats
        _fallback_cache_state["signature"] = _fallback_signature(file_metadata)
        _fallback_cache_state["inflight"] = False


def _schedule_fallback_cache_refresh(force: bool = False) -> None:
    file_metadata = _collect_pdf_metadata()
    signature = _fallback_signature(file_metadata)
    with _fallback_cache_lock:
        if _fallback_cache_state["inflight"]:
            return
        if not force and _fallback_cache_state["signature"] == signature and _fallback_cache_state["stats"] is not None:
            return
        _fallback_cache_state["inflight"] = True

    def _runner():
        try:
            _refresh_fallback_cache()
        except Exception as exc:
            logger.error("Background local corpus refresh failed: %s", exc)
            with _fallback_cache_lock:
                _fallback_cache_state["inflight"] = False

    threading.Thread(target=_runner, daemon=True).start()


def _wait_for_fallback_cache(max_wait_seconds: float = 2.0) -> None:
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        with _fallback_cache_lock:
            if _fallback_cache_state["stats"] is not None:
                return
            inflight = _fallback_cache_state["inflight"]
        if not inflight:
            return
        time.sleep(0.05)


def _schedule_vector_store_refresh(force_reindex: bool = False, recreate_collection_on_sync: bool = True) -> None:
    cfg = _get_milvus_config()
    if cfg is None or _milvus_circuit_open():
        return
    with _background_sync_lock:
        if _background_sync_state["inflight"]:
            return
        _background_sync_state["inflight"] = True

    def _runner():
        global _vector_store_cache
        try:
            store = initialize_vector_store(
                force_reindex=force_reindex,
                recreate_collection_on_sync=recreate_collection_on_sync,
                allow_background_sync=False,
            )
            if store is not None:
                with _vector_store_lock:
                    _vector_store_cache = store
        finally:
            with _background_sync_lock:
                _background_sync_state["inflight"] = False

    threading.Thread(target=_runner, daemon=True).start()


def initialize_vector_store(
    force_reindex: bool = False,
    recreate_collection_on_sync: bool = True,
    allow_background_sync: bool = True,
):
    cfg = _get_milvus_config()
    if cfg is None:
        return None
    if not _milvus_endpoint_reachable(cfg):
        return None

    embeddings = OllamaEmbeddings(model=cfg["model"], base_url=OLLAMA_BASE_URL)
    conn_args = {"uri": cfg["uri"], "token": cfg["token"]}
    file_metadata = _collect_pdf_metadata()

    tracked_hashes = _load_tracking_map()
    auto_sync = _env_bool("ACADEMERAG_AUTO_SYNC_INDEX", default=True)
    should_sync, reason = compute_sync_decision(file_metadata, tracked_hashes, force_reindex)
    should_sync = should_sync and auto_sync

    try:
        if should_sync:
            if allow_background_sync and not force_reindex:
                logger.info("Scheduling background Milvus sync due to reason: %s", reason)
                _schedule_vector_store_refresh(
                    force_reindex=True,
                    recreate_collection_on_sync=recreate_collection_on_sync,
                )
                should_sync = False
            else:
                docs = _load_and_chunk_files(file_metadata)
                if not docs:
                    logger.error("No chunkable PDF content found; cannot build vector index.")
                    return None
                logger.info("Rebuilding Milvus collection due to sync reason: %s", reason)
                ensure_collection_schema(cfg, embeddings, recreate=recreate_collection_on_sync)
                vector_store = Milvus(
                    collection_name=cfg["collection"],
                    embedding_function=embeddings,
                    connection_args={**conn_args, "timeout": MILVUS_INIT_TIMEOUT_SECONDS},
                    auto_id=True,
                    primary_field="pk",
                    text_field="text",
                    vector_field="vector",
                    enable_dynamic_field=True,
                    timeout=MILVUS_INIT_TIMEOUT_SECONDS,
                )
                _ingest_documents_in_batches(vector_store, docs)
                _save_tracking_rows(file_metadata)
                vector_store.similarity_search("index readiness probe", k=1)
                logger.info("Milvus vector store operational.")
                _milvus_health["last_error"] = None
                _milvus_health["unhealthy_until"] = 0.0
                return vector_store

        if not should_sync:
            ensure_collection_schema(cfg, embeddings, recreate=False)
            vector_store = Milvus(
                collection_name=cfg["collection"],
                embedding_function=embeddings,
                connection_args={**conn_args, "timeout": MILVUS_INIT_TIMEOUT_SECONDS},
                primary_field="pk",
                text_field="text",
                vector_field="vector",
                enable_dynamic_field=True,
                timeout=MILVUS_INIT_TIMEOUT_SECONDS,
            )
            if reason == "unchanged":
                logger.info("Milvus index unchanged; using existing collection.")
            elif not auto_sync:
                logger.info("Milvus index auto-sync disabled; using existing collection.")

        vector_store.similarity_search("index readiness probe", k=1)
        logger.info("Milvus vector store operational.")
        _milvus_health["last_error"] = None
        _milvus_health["unhealthy_until"] = 0.0
        return vector_store
    except Exception as exc:
        _mark_milvus_unhealthy(str(exc))
        logger.error("Error initializing vector store: %s", exc)
        return None


def get_vector_store():
    global _vector_store_cache
    with _vector_store_lock:
        if _vector_store_cache is not None:
            return _vector_store_cache
    store = initialize_vector_store(force_reindex=False, allow_background_sync=True)
    if store:
        with _vector_store_lock:
            _vector_store_cache = store
        return store
    if _milvus_cloud_ready():
        logger.error("Failed to create vector store")
    return None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _query_keywords(question: str) -> set[str]:
    return {token for token in _tokenize(question) if token not in STOPWORDS}


def _query_subject_phrase(question: str) -> str | None:
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower().rstrip("?.!"))
    if not normalized:
        return None

    matches = list(re.finditer(r"\b(?:in|of|for)\s+([a-z][a-z0-9 &/-]{4,})$", normalized))
    if not matches:
        return None

    phrase = matches[-1].group(1).strip()
    if " in " in phrase:
        phrase = phrase.rsplit(" in ", 1)[-1].strip()
    for prefix in ("course ", "subject ", "the course ", "the subject "):
        if phrase.startswith(prefix):
            phrase = phrase[len(prefix):].strip()
    return phrase or None


def _is_unit_title_query(question: str) -> bool:
    normalized = (question or "").lower()
    return (
        "unit" in normalized
        and ("title" in normalized or "titles" in normalized or "name" in normalized or "names" in normalized)
    )


def _is_syllabus_query(question: str) -> bool:
    normalized = (question or "").lower()
    return "syllabus" in normalized or "unit" in normalized or "units" in normalized


def _unit_heading_count(text: str) -> int:
    return len(
        re.findall(
            r"\bunit\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\b",
            (text or "").lower(),
        )
    )


def _explicit_unit_title_line_count(text: str) -> int:
    return len(
        re.findall(
            r"(?im)^\s*unit\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\s+[a-z][a-z0-9 ,&()/:-]{3,}$",
            (text or "").lower(),
        )
    )


def _document_score(question: str, doc: Document) -> tuple[int, int, int]:
    text = doc.page_content or ""
    normalized = text.lower()
    subject_phrase = _query_subject_phrase(question)
    tokens = Counter(_tokenize(text))
    keyword_score = sum(min(freq, tokens[token]) for token, freq in Counter(_query_keywords(question)).items())
    boost = 0
    if _is_syllabus_query(question):
        unit_count = _unit_heading_count(text)
        explicit_unit_titles = _explicit_unit_title_line_count(text)
        if explicit_unit_titles:
            boost += explicit_unit_titles * 10
        elif unit_count:
            boost += unit_count
        if "digital logic design" in normalized:
            boost += 4
        if "course objectives" in normalized:
            boost -= 4
        if "program outcomes" in normalized:
            boost -= 4
        if "assessment methodology" in normalized or "written test" in normalized:
            boost -= 5
        if subject_phrase:
            if subject_phrase in normalized:
                boost += 14
            else:
                boost -= 20
    page_number = int((doc.metadata or {}).get("page_number") or 0)
    return (keyword_score + boost, boost, -page_number)


def _has_explicit_support(question: str, docs: list[Document]) -> bool:
    if not docs:
        return False

    if _is_syllabus_query(question):
        return any(_explicit_unit_title_line_count(doc.page_content) >= 1 for doc in docs)

    keywords = _query_keywords(question)
    if not keywords:
        return False

    for doc in docs:
        doc_tokens = set(_tokenize(doc.page_content))
        overlap = len(keywords & doc_tokens)
        if overlap >= max(2, min(4, len(keywords))):
            return True
    return False


def _augment_docs_for_syllabus(question: str, docs: list[Document]) -> list[Document]:
    if not _is_syllabus_query(question) or not docs:
        return docs

    corpus = _fallback_chunk_corpus()
    by_page: dict[tuple[object, object], Document] = {}
    for doc in corpus:
        key = ((doc.metadata or {}).get("document_path"), (doc.metadata or {}).get("page_number"))
        existing = by_page.get(key)
        if existing is None:
            by_page[key] = doc
            continue
        current_index = int((doc.metadata or {}).get("chunk_index") or 0)
        existing_index = int((existing.metadata or {}).get("chunk_index") or 0)
        if current_index < existing_index:
            by_page[key] = doc
    augmented = list(docs)
    seen = {
        ((doc.metadata or {}).get("document_path"), (doc.metadata or {}).get("page_number"), (doc.metadata or {}).get("chunk_index"))
        for doc in docs
    }

    for doc in docs:
        page_number = (doc.metadata or {}).get("page_number")
        document_path = (doc.metadata or {}).get("document_path")
        if not document_path or not isinstance(page_number, int):
            continue
        if _explicit_unit_title_line_count(doc.page_content) < 1:
            continue
        next_doc = by_page.get((document_path, page_number + 1))
        if not next_doc:
            continue
        next_key = (
            (next_doc.metadata or {}).get("document_path"),
            (next_doc.metadata or {}).get("page_number"),
            (next_doc.metadata or {}).get("chunk_index"),
        )
        if next_key not in seen:
            augmented.append(next_doc)
            seen.add(next_key)
    return augmented


@lru_cache(maxsize=1)
def _raw_page_text_map(signature: tuple[tuple[str, str], ...]) -> dict[tuple[str, int], str]:
    pages: dict[tuple[str, int], str] = {}
    file_metadata = _collect_pdf_metadata()
    for item in file_metadata:
        reader = PdfReader(item["path"])
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages[(item["relative_path"], page_number)] = text
    return pages


def _page_text_map() -> dict[tuple[str, int], str]:
    return _raw_page_text_map(_fallback_signature(_collect_pdf_metadata()))


_SYLLABUS_NOISE_HEADINGS = (
    "text books",
    "reference books",
    "references",
    "text and reference books",
    "web-based/online resources",
    "based/online resources",
    "web-based resources",
    "suggested list of students activity",
    "suggested list of student activities",
    "equipment / facilities required to conduct the practical portion",
    "equipment / facilities required to conduct the practical portion ",
    "equipment / facilities required to conduct the practical portion",
    "equipment / facilities required to conduct the practical portion:",
    "equipment / facilities required to conduct the practical portion",
    "equipment / facilities required to conduct the practical portion",
    "equipment / facilities required to conduct the practical portion ",
    "equipment / facilities required to conduct the practical portion  ",
    "equipment / facilities required to conduct the practical portion",
    "equipment / facilities required to conduct the practical portion",
    "execution notes",
    "execution guidelines",
    "continuous assessment pattern",
    "allocation of marks",
)


def _is_syllabus_noise_heading(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", (line or "").strip().lower()).rstrip(":")
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in _SYLLABUS_NOISE_HEADINGS)


def _is_page_header_line(line: str) -> bool:
    normalized = re.sub(r"\s+", " ", (line or "").strip().lower())
    return bool(
        normalized
        and (
            normalized.startswith("directorate of technical education")
            or normalized.startswith("2023 regulation")
            or normalized == "theory 3 0 0 3"
            or normalized == "practicum 1 0 4 3"
            or normalized == "practical 0 0 4 2"
            or re.fullmatch(r"\d+", normalized)
        )
    )


def _is_syllabus_noise_item(line: str) -> bool:
    stripped = (line or "").strip()
    normalized = stripped.lower()
    if not stripped:
        return True
    if _is_page_header_line(stripped):
        return True
    if re.match(r"^(?:https?://|www\.)", normalized):
        return True
    if re.match(r"^[\d]+\s*[\.\)]\s+", stripped):
        return True
    if re.match(r"^[•●\-]\s*", stripped):
        return True
    if normalized.startswith(("hardware requirement", "software requirement", "the following student")):
        return True
    bibliography_markers = (
        "edition",
        "press",
        "pearson",
        "mc-graw",
        "mcgraw",
        "wiley",
        "springer",
        "oxford",
        "universities press",
        "university press",
        "o'reilly",
        "oreilly",
        "publication",
        "publications",
        "education services",
        "pvt. ltd",
    )
    if any(marker in normalized for marker in bibliography_markers):
        return True
    if re.search(r"\b(19|20)\d{2}\b", normalized):
        return True
    return False


def _clean_syllabus_text(text: str) -> str:
    lines = [line.rstrip() for line in (text or "").splitlines()]
    cleaned: list[str] = []
    skipping_noise = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        if _is_page_header_line(line):
            continue

        if _is_syllabus_noise_heading(line):
            skipping_noise = True
            continue

        if skipping_noise:
            if re.match(r"(?i)^unit\s+[ivxlcdm]+\b", line) or re.match(r"(?i)^total\s+(?:hours|periods)\b", line):
                skipping_noise = False
            elif _is_syllabus_noise_heading(line) or _is_syllabus_noise_item(line):
                continue
            else:
                # Resume once the page returns to regular syllabus content.
                skipping_noise = False

        if cleaned and cleaned[-1] == "" and line == "":
            continue
        cleaned.append(line)

    compacted = "\n".join(cleaned)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted)
    return compacted.strip()


def _extract_syllabus_text(question: str) -> str | None:
    if not _is_syllabus_query(question):
        return None

    subject_phrase = _query_subject_phrase(question)
    if not subject_phrase:
        return None

    pages = _page_text_map()
    ordered_pages = sorted(pages.items(), key=lambda item: (item[0][0], item[0][1]))

    start_index = None
    for index, ((document_path, page_number), text) in enumerate(ordered_pages):
        normalized = text.lower()
        if subject_phrase in normalized and _unit_heading_count(text) > 0:
            start_index = index
            break
    if start_index is None:
        return None

    collected_pages: list[str] = []
    for index in range(start_index, min(start_index + 4, len(ordered_pages))):
        (document_path, page_number), text = ordered_pages[index]
        normalized = text.lower()
        if index > start_index and re.search(r"\b\d{10}\b", text) and subject_phrase not in normalized and _unit_heading_count(text) == 0:
            break
        collected_pages.append(text)
        if "total hours" in normalized or "total periods" in normalized:
            break

    combined = "\n".join(collected_pages)
    unit_start = re.search(r"(?im)^\s*unit\s+i\b", combined)
    total_match = re.search(r"(?im)^\s*total\s+(?:hours|periods)\b.*$", combined)
    if unit_start:
        start_pos = unit_start.start()
        end_pos = total_match.end() if total_match else len(combined)
        extracted = _clean_syllabus_text(combined[start_pos:end_pos])
        if extracted:
            return extracted
    return _clean_syllabus_text(combined) or None


def _fallback_chunk_corpus() -> tuple[Document, ...]:
    file_metadata = _collect_pdf_metadata()
    signature = _fallback_signature(file_metadata)
    with _fallback_cache_lock:
        cached_signature = _fallback_cache_state["signature"]
        cached_corpus = _fallback_cache_state["corpus"]
        has_cache = bool(cached_corpus)
    if cached_signature != signature:
        _schedule_fallback_cache_refresh(force=True)
    if has_cache:
        return cached_corpus
    _wait_for_fallback_cache()
    with _fallback_cache_lock:
        warmed_corpus = _fallback_cache_state["corpus"]
    if warmed_corpus:
        return warmed_corpus
    logger.warning("Local corpus cache cold-start; building synchronously once.")
    _refresh_fallback_cache()
    with _fallback_cache_lock:
        warmed_corpus = _fallback_cache_state["corpus"]
    if warmed_corpus:
        return warmed_corpus
    logger.warning("Local corpus cache is warming; retrieval may have limited results temporarily.")
    return tuple()


def _fallback_corpus_stats() -> dict:
    with _fallback_cache_lock:
        stats = _fallback_cache_state["stats"]
    if stats is not None:
        return stats
    _wait_for_fallback_cache()
    with _fallback_cache_lock:
        stats = _fallback_cache_state["stats"]
    if stats is not None:
        return stats
    logger.warning("Local corpus stats unavailable on cold-start; building synchronously once.")
    _refresh_fallback_cache()
    with _fallback_cache_lock:
        stats = _fallback_cache_state["stats"]
    if stats is not None:
        return stats
    corpus = _fallback_chunk_corpus()
    return _build_fallback_stats_from_docs(corpus)


def _bm25_score(query_terms: list[str], doc_index: int, stats: dict) -> float:
    if not query_terms or stats["doc_count"] == 0:
        return 0.0

    tf = stats["term_frequencies"][doc_index]
    doc_length = len(stats["tokenized_docs"][doc_index]) or 1
    avg_doc_length = stats["avg_doc_length"] or 1.0
    score = 0.0

    for term in query_terms:
        freq = tf.get(term, 0)
        if freq == 0:
            continue
        df = stats["document_frequencies"].get(term, 0)
        idf = max(0.0, math.log(1.0 + ((stats["doc_count"] - df + 0.5) / (df + 0.5))))
        numerator = freq * (BM25_K1 + 1.0)
        denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * (doc_length / avg_doc_length))
        score += idf * (numerator / denominator)

    return score


def _generic_retrieval_boost(question: str, doc: Document) -> float:
    text = doc.page_content or ""
    normalized = text.lower()
    subject_phrase = _query_subject_phrase(question)
    boost = 0.0

    if subject_phrase:
        if subject_phrase in normalized:
            boost += 3.5
        else:
            boost -= 1.5

    query_text = (question or "").lower()
    if "lab" in query_text and "practical" in normalized:
        boost += 1.0
    if "objective" in query_text and "course objectives" in normalized:
        boost += 2.0
    if "experiment" in query_text and ("ex no" in normalized or "experiment" in normalized):
        boost += 2.0
    if "syllabus" in query_text and "total periods" in normalized:
        boost += 0.5

    return boost


def _fallback_retrieve_docs(question: str, k: int) -> list[Document]:
    _schedule_fallback_cache_refresh()
    stats = _fallback_corpus_stats()
    corpus = stats["corpus"]
    if not corpus:
        return []

    query_tokens = _tokenize(question)
    if not query_tokens:
        return list(corpus[:k])

    scored = []
    query_terms = [token for token in query_tokens if token not in STOPWORDS]
    for index, doc in enumerate(corpus):
        lexical_score = _bm25_score(query_terms, index, stats)
        heuristic_score, heuristic_boost, page_bias = _document_score(question, doc)
        score = lexical_score + _generic_retrieval_boost(question, doc)
        if _is_syllabus_query(question):
            score += heuristic_boost
        else:
            score += heuristic_score * 0.15
        if score > 0:
            scored.append((score, heuristic_boost, page_bias, doc))

    if not scored:
        return list(corpus[:k])
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    primary_docs = [doc for _, _, _, doc in scored[:k]]
    return _expand_neighbor_chunks(primary_docs, max_docs=max(k, 4))


def _expand_neighbor_chunks(docs: list[Document], max_docs: int) -> list[Document]:
    if not docs:
        return docs

    corpus = _fallback_chunk_corpus()
    index_by_key = {
        (
            (doc.metadata or {}).get("document_path"),
            (doc.metadata or {}).get("page_number"),
            (doc.metadata or {}).get("chunk_index"),
        ): doc
        for doc in corpus
    }
    expanded = list(docs)
    seen = set(index_by_key_key for index_by_key_key in [
        (
            (doc.metadata or {}).get("document_path"),
            (doc.metadata or {}).get("page_number"),
            (doc.metadata or {}).get("chunk_index"),
        )
        for doc in docs
    ])

    for doc in docs:
        if len(expanded) >= max_docs:
            break
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        page_number = metadata.get("page_number")
        chunk_index = metadata.get("chunk_index")
        if not document_path or not isinstance(page_number, int) or not isinstance(chunk_index, int):
            continue
        for neighbor_chunk_index in (chunk_index - 1, chunk_index + 1):
            key = (document_path, page_number, neighbor_chunk_index)
            neighbor = index_by_key.get(key)
            if neighbor and key not in seen:
                expanded.append(neighbor)
                seen.add(key)
                if len(expanded) >= max_docs:
                    break

    return expanded[:max_docs]


def _retrieve_docs(question: str) -> list[Document]:
    k = _compute_dynamic_top_k(question)
    started = time.monotonic()

    store = get_vector_store()
    if not store:
        fallback_docs = _fallback_retrieve_docs(question, k)
        logger.warning(
            "Vector store unavailable. Using local fallback retrieval with %s document(s).",
            len(fallback_docs),
        )
        return fallback_docs

    docs = []
    try:
        scored = store.similarity_search_with_relevance_scores(question, k=k)
        docs = [doc for doc, score in scored if score >= RELEVANCE_SCORE_THRESHOLD]
    except Exception as exc:
        logger.warning("Milvus relevance search failed (%s); trying similarity fallback.", exc)
        try:
            docs = store.similarity_search(question, k=k)
        except Exception as search_exc:
            logger.error("Milvus similarity fallback failed: %s", search_exc)
            docs = []
    logger.info(
        "Retrieval diagnostics: top_k=%s threshold=%.2f returned=%s latency_ms=%.1f",
        k,
        RELEVANCE_SCORE_THRESHOLD,
        len(docs),
        (time.monotonic() - started) * 1000.0,
    )
    if docs:
        return docs

    fallback_docs = _fallback_retrieve_docs(question, k)
    logger.info(
        "Milvus returned no results. Local fallback returned %s document(s).",
        len(fallback_docs),
    )
    return fallback_docs


def get_retrieval_diagnostics() -> dict:
    should_rebuild, reason = compute_rebuild_state(force_reindex=False)
    return {
        "collection": COLLECTION_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "chunk_profile": _chunk_profile(),
        "base_top_k": TOP_K,
        "dynamic_top_k_min": DYNAMIC_TOP_K_MIN,
        "dynamic_top_k_max": DYNAMIC_TOP_K_MAX,
        "score_threshold": RELEVANCE_SCORE_THRESHOLD,
        "should_rebuild": should_rebuild,
        "rebuild_reason": reason,
        "milvus_cloud_ready": _milvus_cloud_ready(),
    }


def _build_qa_chain():
    prompt = ChatPromptTemplate.from_template(
        """
You are an intelligent College AI Assistant.
Answer purely based on the context below.
If the context does not contain enough information, say:
I am not trained on this data source or the uploaded documents do not contain this information.
Do not use outside knowledge.

Context:
{context}

Question:
{question}

Answer:
"""
    )
    return prompt


def _groq_enabled() -> bool:
    if _env_bool("ACADEMERAG_USE_GROQ_CLOUD", default=False):
        return True
    return LLM_PROVIDER == "groq"


def _create_llm_client(provider: str):
    if provider == "groq":
        _validate_groq_base_url()
        if ChatOpenAI is None:
            raise RuntimeError(
                "Groq provider requires 'langchain-openai'. Install dependencies from requirements_django.txt."
            )
        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is required when Groq provider is enabled.")
        return ChatOpenAI(
            model=GROQ_MODEL,
            temperature=LLM_TEMPERATURE,
            api_key=GROQ_API_KEY,
            base_url=GROQ_BASE_URL,
            timeout=GROQ_REQUEST_TIMEOUT_SECONDS,
            max_retries=1,
        )
    if provider != "ollama":
        raise RuntimeError(f"Unsupported LLM provider: {provider}")
    return ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=LLM_TEMPERATURE)


def _preferred_llm_providers() -> list[str]:
    if _groq_enabled():
        ollama_ready = _ollama_reachable()
        if ollama_ready:
            return ["groq", "ollama"]
        return ["groq"]
    return ["ollama"]


def _validate_groq_base_url() -> None:
    parsed = urlparse(GROQ_BASE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(
            "Invalid GROQ_BASE_URL. Expected an OpenAI-compatible API base URL, "
            "for example: https://api.groq.com/openai/v1"
        )
    if "console.groq.com" in parsed.netloc:
        raise RuntimeError(
            "GROQ_BASE_URL points to Groq Console, not the API endpoint. "
            "Use: https://api.groq.com/openai/v1"
        )
    if "/openai/v1" not in parsed.path:
        raise RuntimeError(
            "GROQ_BASE_URL must include '/openai/v1'. "
            "Use: https://api.groq.com/openai/v1"
        )


def _ollama_reachable(timeout_seconds: float = 1.0) -> bool:
    health_url = OLLAMA_BASE_URL.rstrip("/") + "/"
    try:
        with urlopen(health_url, timeout=timeout_seconds) as response:  # nosec B310
            return 200 <= response.status < 500
    except (URLError, TimeoutError, OSError):
        return False


def _invoke_with_provider_failover(context: str, question: str) -> str:
    prompt = _build_qa_chain()
    payload = {"context": context, "question": question}
    failures = []

    for provider in _preferred_llm_providers():
        try:
            llm = _create_llm_client(provider)
            chain = prompt | llm | StrOutputParser()
            if provider == "groq":
                logger.info("Using Groq cloud LLM provider.")
            return chain.invoke(payload)
        except Exception as exc:
            failures.append((provider, str(exc)))
            logger.warning("LLM provider '%s' failed; trying fallback. Error: %s", provider, exc)

    details = "; ".join(f"{provider}={error}" for provider, error in failures) or "unknown error"
    raise RuntimeError(f"All LLM providers failed: {details}")


def _stream_with_provider_failover(context: str, question: str):
    prompt = _build_qa_chain()
    payload = {"context": context, "question": question}
    providers = _preferred_llm_providers()
    failures = []

    for index, provider in enumerate(providers):
        emitted = False
        try:
            llm = _create_llm_client(provider)
            chain = prompt | llm | StrOutputParser()
            if provider == "groq":
                logger.info("Using Groq cloud LLM provider for streaming.")
            for chunk in chain.stream(payload):
                emitted = True
                yield chunk
            return
        except Exception as exc:
            failures.append((provider, str(exc)))
            can_fallback = index < len(providers) - 1 and not emitted
            if can_fallback:
                logger.warning(
                    "Streaming LLM provider '%s' failed before output; trying fallback. Error: %s",
                    provider,
                    exc,
                )
                continue
            logger.error("Streaming LLM provider '%s' failed: %s", provider, exc)
            raise

    details = "; ".join(f"{provider}={error}" for provider, error in failures) or "unknown error"
    raise RuntimeError(f"All streaming LLM providers failed: {details}")


def get_optimized_response(question: str) -> str:
    syllabus_text = _extract_syllabus_text(question)
    if syllabus_text:
        return syllabus_text
    docs = _augment_docs_for_syllabus(question, _retrieve_docs(question))
    if not docs:
        return INSUFFICIENT_CONTEXT_MESSAGE
    context = "\n\n".join(doc.page_content for doc in docs)
    return _invoke_with_provider_failover(context=context, question=question)


def stream_optimized_response(question: str):
    syllabus_text = _extract_syllabus_text(question)
    if syllabus_text:
        yield syllabus_text
        return
    docs = _augment_docs_for_syllabus(question, _retrieve_docs(question))
    if not docs:
        yield INSUFFICIENT_CONTEXT_MESSAGE
        return
    context = "\n\n".join(doc.page_content for doc in docs)
    for chunk in _stream_with_provider_failover(context=context, question=question):
        yield chunk


def get_retriever():
    store = get_vector_store()
    if not store:
        return None
    return store.as_retriever(search_kwargs={"k": TOP_K})


_schedule_fallback_cache_refresh()
