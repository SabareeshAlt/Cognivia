import hashlib
import logging
import math
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import os
import re
import socket
import threading
import time
try:
    import magic
except ImportError:
    import sys
    from types import ModuleType
    dummy_magic = ModuleType("magic")
    def from_file(filename, mime=False):
        import mimetypes
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"
    dummy_magic.from_file = from_file
    sys.modules["magic"] = dummy_magic
    import magic
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Optional, Any, List, Tuple, Union, Set

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_milvus import Milvus
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient, connections
from pypdf import PdfReader
from rag.pdf_sandbox import extract_pdf_text_sandboxed

os.environ["MILVUS_ASYNC"] = "0"

logger = logging.getLogger(__name__)

# Global state for lazy-loaded CrossEncoder
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

INSUFFICIENT_CONTEXT_MESSAGE = "Not found in the provided documents."

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


# Cloud normalization logic stripped


COLLECTION_NAME = _env_str("COLLECTION_NAME", "academerag")
EMBEDDING_MODEL = _env_str("EMBEDDING_MODEL", "nomic-embed-text")
LLM_MODEL = _env_str("ACADEMERAG_LLM_MODEL", "llama3.1:latest")
OLLAMA_BASE_URL = _env_str("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_TEMPERATURE = _env_float("ACADEMERAG_LLM_TEMPERATURE", 0.1)
LLM_PROVIDER = "ollama"
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
    docs_dir_prefix = os.path.normcase(os.path.abspath(DOCUMENTS_DIR) + os.sep)
    for path in pdf_files:
        name = os.path.basename(path).lower()
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = path
            continue
        # Prefer managed documents/ copies over root duplicates.
        normalized = os.path.normcase(os.path.abspath(path))
        if normalized.startswith(docs_dir_prefix):
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


def _available_sources() -> set[str]:
    return {os.path.basename(path) for path in get_pdf_files()}


def _extract_target_sources(question: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
    if not normalized:
        return set()

    available_sources = sorted(_available_sources())
    if not available_sources:
        return set()

    by_lower = {source.lower(): source for source in available_sources}
    targets: set[str] = set()

    for source_lower, source in by_lower.items():
        if source_lower in normalized:
            targets.add(source)

    ordinal_to_number = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
    }
    number_candidates: set[int] = set()

    for match in re.findall(r"\brag\s*sample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bsample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bpdf\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:pdf|document|sample)\b", normalized):
        number_candidates.add(int(match))

    for word, number in ordinal_to_number.items():
        if re.search(rf"\b{word}\s+(?:pdf|document|sample)\b", normalized):
            number_candidates.add(number)

    for number in number_candidates:
        candidate = f"RAG sample {number}.pdf".lower()
        source = by_lower.get(candidate)
        if source:
            targets.add(source)

    return targets


def _milvus_escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _milvus_source_filter_expr(target_sources: set[str]) -> str | None:
    if not target_sources:
        return None
    ordered = sorted(target_sources)
    if len(ordered) == 1:
        return f'source == "{_milvus_escape_literal(ordered[0])}"'
    joined = ", ".join(f'"{_milvus_escape_literal(source)}"' for source in ordered)
    return f"source in [{joined}]"


def _doc_source(doc: Document) -> str:
    return str((doc.metadata or {}).get("source") or "")


def _filter_docs_by_sources(docs: list[Document], target_sources: set[str]) -> list[Document]:
    if not target_sources:
        return docs
    allowed = {source.lower() for source in target_sources}
    return [doc for doc in docs if _doc_source(doc).lower() in allowed]


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
    """
    Loads PDF files, extracts text, and chunks it using RecursiveCharacterTextSplitter.
    Fixes cross-page continuity by accumulating text across pages instead of flushing per page.
    Tracks page boundaries via character offsets to accurately assign `page_number` to chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    all_chunks = []
    logger.info("Starting structure-aware parse/chunk stage for %s file(s).", len(file_metadata))
    
    # regex for section detection
    section_pattern = re.compile(r'(?i)^(UNIT\s+[IVXLCDM\d]+.*?|COURSE OBJECTIVES|OUTCOMES|REFERENCES|LAB|ASSESSMENT|PRACTICAL)\s*$')
    
    for item in file_metadata:
        file_start = time.monotonic()
        logger.info("Parsing file: %s", item["relative_path"])
        
        path = item["path"]
        # Security: Validate file magic bytes
        with open(path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                logger.error("Invalid file signature for %s. Expected '%%PDF-'. Skipping.", item['relative_path'])
                continue
                
        # Security: Validate MIME type using python-magic
        mime = magic.from_file(path, mime=True)
        if mime != 'application/pdf':
            logger.error("Invalid MIME type '%s' for %s. Expected 'application/pdf'. Skipping.", mime, item['relative_path'])
            continue
            
        try:
            pages = extract_pdf_text_sandboxed(path)
        except Exception as e:
            logger.error("Sandbox extraction failed for %s: %s. Skipping.", item['relative_path'], e)
            continue
        page_count = len(pages)
        
        current_subject = item["source"].replace('.pdf', '')
        current_unit_number = None
        current_unit_title = None
        current_section_type = "GENERAL"
        
        current_section_text = ""
        page_boundaries = []  # List of tuples: (char_offset, page_number)
        chunk_index = 0
        
        def flush_section():
            nonlocal chunk_index, current_section_text, page_boundaries
            if not current_section_text.strip():
                return
            
            chunks = splitter.split_text(current_section_text)
            search_start = 0
            for c in chunks:
                pos = current_section_text.find(c, search_start)
                if pos == -1:
                    pos = search_start
                else:
                    search_start = pos + 1
                    
                # Find page number for this chunk's start position
                page_num = 1
                for boundary_pos, p_num in page_boundaries:
                    if boundary_pos <= pos:
                        page_num = p_num
                    else:
                        break
                        
                all_chunks.append(Document(
                    page_content=c,
                    metadata={
                        "source": item["source"],
                        "subject_name": current_subject,
                        "document_path": item["relative_path"],
                        "document_hash": item["content_hash"],
                        "page_number": page_num,
                        "unit_number": current_unit_number,
                        "unit_title": current_unit_title,
                        "section_type": current_section_type,
                        "chunk_index": chunk_index,
                    }
                ))
                chunk_index += 1
                
            current_section_text = ""
            page_boundaries = []

        for page_info in pages:
            idx = page_info["page_number"]
            page_text = page_info["text"] or ""
            if not page_text.strip():
                continue
                
            lines = page_text.split('\n')
            
            # Record page boundary for this new page at the current text offset
            if not page_boundaries or page_boundaries[-1][0] < len(current_section_text):
                page_boundaries.append((len(current_section_text), idx))
            elif page_boundaries:
                # Update page number if the offset hasn't advanced (e.g. previous page was empty)
                page_boundaries[-1] = (len(current_section_text), idx)
            else:
                page_boundaries.append((len(current_section_text), idx))
                
            for line in lines:
                match = section_pattern.match(line.strip())
                if match:
                    flush_section()
                    heading = match.group(1).upper()
                    if heading.startswith("UNIT"):
                        current_section_type = "UNIT"
                        parts = heading.split(maxsplit=2)
                        current_unit_number = parts[1] if len(parts) > 1 else None
                        current_unit_title = heading
                    else:
                        current_section_type = heading
                        current_unit_number = None
                        current_unit_title = None
                        
                    # After flushing, text is empty, so record a new page boundary at offset 0
                    page_boundaries.append((len(current_section_text), idx))
                    current_section_text += line + "\n"
                else:
                    current_section_text += line + "\n"
            
            if idx % 10 == 0 or idx == page_count:
                logger.info("  %s page(s) processed for %s", idx, item["source"])
                
        # Final flush for any remaining text in the document
        flush_section()
        
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


def _ingest_documents_with_client(cfg: dict, embeddings, docs) -> None:
    # Assume _connect_milvus_client_with_timeout, MILVUS_INIT_TIMEOUT_SECONDS,
    # INGEST_BATCH_SIZE, INGEST_MAX_SECONDS are available.
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=MILVUS_INIT_TIMEOUT_SECONDS)
    total = len(docs)
    start = time.monotonic()
    logger.info(
        "Starting Milvus client ingestion for %s chunk(s) with batch size %s (timeout %.0fs).",
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
        batch_texts = [doc.page_content for doc in batch]
        batch_vectors = embeddings.embed_documents(batch_texts)
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"Embedding size mismatch: got {len(batch_vectors)} vectors for {len(batch)} chunks"
            )
        
        payload = []
        for doc, vector in zip(batch, batch_vectors):
            meta = doc.metadata or {}
            row = {
                "text": doc.page_content, 
                "vector": vector,
                "source": str(meta.get("source", ""))[:1024],
                "page_number": int(meta.get("page_number", 0)),
                "chunk_index": int(meta.get("chunk_index", 0))
            }
            # Put remaining metadata fields into dynamic fields
            for k, v in meta.items():
                if k not in ["source", "page_number", "chunk_index"]:
                    row[k] = v
                    
            payload.append(row)
            
        batch_start = time.monotonic()
        client.insert(collection_name=cfg["collection"], data=payload)
        completed = min(offset + len(batch), total)
        percent = (completed / total) * 100.0
        batch_elapsed = time.monotonic() - batch_start
        avg_per_chunk = (time.monotonic() - start) / completed
        remaining_chunks = total - completed
        eta = remaining_chunks * avg_per_chunk
        logger.info(
            "Client ingestion progress: %s/%s chunks (%.1f%%) | batch %.2fs | elapsed %.1fs | eta %.1fs",
            completed,
            total,
            percent,
            batch_elapsed,
            time.monotonic() - start,
            eta,
        )
    logger.info("Milvus client ingestion completed in %.1fs.", time.monotonic() - start)


def _build_langchain_vector_store(cfg: dict, embeddings: OllamaEmbeddings) -> Milvus:
    conn_args = {"uri": cfg["uri"], "token": cfg["token"]}
    _ensure_langchain_milvus_connection(cfg)
    return Milvus(
        collection_name=cfg["collection"],
        embedding_function=embeddings,
        connection_args={**conn_args, "alias": "default", "timeout": MILVUS_INIT_TIMEOUT_SECONDS},
        primary_field="pk",
        text_field="text",
        vector_field="vector",
        enable_dynamic_field=True,
        timeout=MILVUS_INIT_TIMEOUT_SECONDS,
    )


def _get_milvus_config():
    milvus_uri = _env_str("ACADEMERAG_MILVUS_URI", "http://milvus:19530")
    milvus_token = _env_str("ACADEMERAG_MILVUS_TOKEN", "")
    logger.info("Using local Milvus Standalone vector store at %s", milvus_uri)
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


def _ensure_langchain_milvus_connection(cfg: dict) -> None:
    try:
        connections.disconnect(alias="default")
    except Exception:
        pass
    connections.connect(
        alias="default",
        uri=cfg["uri"],
        token=cfg["token"],
        timeout=MILVUS_INIT_TIMEOUT_SECONDS,
    )


def _mark_milvus_unhealthy(error: str) -> None:
    _milvus_health["last_error"] = error
    _milvus_health["unhealthy_until"] = time.monotonic() + MILVUS_CIRCUIT_BREAKER_SECONDS


def _milvus_circuit_open() -> bool:
    return time.monotonic() < _milvus_health["unhealthy_until"]





def collection_exists(cfg: dict) -> bool:
    return _connect_milvus_client(cfg).has_collection(cfg["collection"])


def _get_embedding_dimension(embeddings: OllamaEmbeddings) -> int:
    return len(embeddings.embed_query("dimension probe"))


def ensure_collection_schema(cfg: dict, embeddings, recreate: bool = False) -> bool:
    """Ensure collection exists with explicit schema before ingestion."""
    # Assume _connect_milvus_client, _wait_for_collection_absence, 
    # _wait_for_collection_presence, _get_embedding_dimension are available.
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
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=1024),
        FieldSchema(name="page_number", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
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

    # Add scalar indexes for these fields using client.create_index() to optimize metadata filtering.
    scalar_index_params = MilvusClient.prepare_index_params()
    scalar_index_params.add_index(field_name="source", index_name="source_idx")
    scalar_index_params.add_index(field_name="page_number", index_name="page_number_idx")
    scalar_index_params.add_index(field_name="chunk_index", index_name="chunk_index_idx")
    
    client.create_index(collection_name=cfg["collection"], index_params=scalar_index_params)
    
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
    return _get_cloud_config() is not None


def _build_fallback_stats_from_docs(docs: tuple[Document, ...]) -> dict[str, Any]:
    """
    Build optimized inverted index and corpus statistics for fast BM25 retrieval.
    This replaces the previous slow list-of-Counters approach and executes efficiently.
    """
    # inverted_index maps term -> list of (doc_index, term_frequency)
    inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_lengths = []
    total_length = 0

    # We rely on the existing _tokenize from Milvus.py context
    for idx, doc in enumerate(docs):
        tokens = _tokenize(doc.page_content)
        length = len(tokens)
        doc_lengths.append(length)
        total_length += length
        
        tf = Counter(tokens)
        for token, count in tf.items():
            inverted_index[token].append((idx, count))

    avg_doc_length = (total_length / len(docs)) if docs else 0.0
    
    return {
        "corpus": docs,
        "inverted_index": dict(inverted_index),
        "doc_lengths": doc_lengths,
        "avg_doc_length": avg_doc_length,
        "doc_count": len(docs),
    }


def _fallback_signature(file_metadata: list[dict]) -> tuple[tuple[str, str], ...]:
    return tuple((item["relative_path"], item["content_hash"]) for item in file_metadata)



import pickle

BM25_INDEX_FILE = os.path.join(PROJECT_ROOT, "bm25_index.pkl")

def _refresh_fallback_cache() -> None:
    file_metadata = _collect_pdf_metadata()
    docs = tuple(_load_and_chunk_files(file_metadata))
    stats = _build_fallback_stats_from_docs(docs)
    signature = _fallback_signature(file_metadata)
    
    with _fallback_cache_lock:
        _fallback_cache_state["corpus"] = docs
        _fallback_cache_state["stats"] = stats
        _fallback_cache_state["signature"] = signature
        _fallback_cache_state["inflight"] = False

    try:
        import filelock
        lock = filelock.FileLock(BM25_INDEX_FILE + ".lock")
        with lock.acquire(timeout=30):
            tmp_file = BM25_INDEX_FILE + f".{os.getpid()}.tmp"
            with open(tmp_file, "wb") as f:
                pickle.dump({
                    "signature": signature,
                    "corpus": docs,
                    "stats": stats
                }, f)
            os.replace(tmp_file, BM25_INDEX_FILE)
    except Exception as e:
        logger.warning(f"Failed to persist BM25 index: {e}")

def _load_persisted_bm25() -> bool:
    if not os.path.exists(BM25_INDEX_FILE):
        return False
    try:
        with open(BM25_INDEX_FILE, "rb") as f:
            data = pickle.load(f)
            
        current_sig = _fallback_signature(_collect_pdf_metadata())
        if data["signature"] == current_sig:
            with _fallback_cache_lock:
                _fallback_cache_state["corpus"] = data["corpus"]
                _fallback_cache_state["stats"] = data["stats"]
                _fallback_cache_state["signature"] = data["signature"]
                _fallback_cache_state["inflight"] = False
            return True
    except Exception as e:
        logger.warning(f"Failed to load persisted BM25 index: {e}")
    return False

def _init_bm25_index_at_startup() -> None:
    if _load_persisted_bm25():
        logger.info("BM25 index loaded successfully at startup.")
        return

    logger.info("BM25 index missing or stale at startup. Building synchronously under lock.")
    try:
        import filelock
        lock = filelock.FileLock(BM25_INDEX_FILE + ".build.lock")
        with lock.acquire(timeout=300):
            if _load_persisted_bm25():
                logger.info("BM25 index built by another worker. Loaded successfully.")
                return
            logger.info("Building BM25 index...")
            _refresh_fallback_cache()
    except Exception as e:
        logger.error(f"Failed to initialize BM25 index at startup: {e}")

def _fallback_chunk_corpus() -> tuple[Document, ...]:
    with _fallback_cache_lock:
        cached_corpus = _fallback_cache_state["corpus"]
        
    if cached_corpus:
        return cached_corpus
        
    logger.warning("Local BM25 corpus unavailable; failing fast.")
    return tuple()

def _fallback_corpus_stats() -> dict:
    with _fallback_cache_lock:
        stats = _fallback_cache_state["stats"]
    if stats is not None:
        return stats
        
    logger.warning("Local BM25 index unavailable; failing fast.")
    return {"corpus": tuple(), "inverted_index": {}, "doc_lengths": [], "avg_doc_length": 1.0, "doc_count": 0}


def _bm25_score(query_terms: list[str], doc_index: int, stats: dict) -> float:
    """
    Retained for backwards compatibility if any external caller/test references it,
    but no longer directly used by _fallback_retrieve_docs optimization.
    """
    if not query_terms or stats.get("doc_count", 0) == 0:
        return 0.0

    inverted_index = stats.get("inverted_index", {})
    doc_lengths = stats.get("doc_lengths", [])
    avg_doc_length = stats.get("avg_doc_length", 1.0)
    doc_count = stats.get("doc_count", 0)
    
    score = 0.0
    for term in query_terms:
        if term not in inverted_index:
            continue
        postings = inverted_index[term]
        df = len(postings)
        freq = next((f for d, f in postings if d == doc_index), 0)
        if freq == 0:
            continue
            
        idf = max(0.0, math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5))))
        doc_length = doc_lengths[doc_index] if doc_index < len(doc_lengths) else 1
        numerator = freq * (BM25_K1 + 1.0)
        denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * (doc_length / avg_doc_length))
        score += idf * (numerator / denominator)
        
    return score





def _fallback_retrieve_docs(question: str, k: int, target_sources: set[str] | None = None) -> list[Document]:
    """
    Retrieve documents using the inverted index for optimized BM25 scoring.
    Designed to act as the sparse leg of the parallel hybrid search.
    """
    stats = _fallback_corpus_stats()
    corpus = stats["corpus"]
    if not corpus:
        return []
        
    allowed_sources = {source.lower() for source in (target_sources or set())}
    
    query_tokens = _tokenize(question)
    query_terms = [token for token in query_tokens if token not in STOPWORDS]

    if not query_terms:
        # Fallback to returning first k if no usable terms are found
        filtered = [
            doc for doc in corpus 
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    inverted_index = stats["inverted_index"]
    doc_lengths = stats["doc_lengths"]
    avg_doc_length = stats["avg_doc_length"] or 1.0
    doc_count = stats["doc_count"]

    # Calculate BM25 scores efficiently using the inverted index
    scores: dict[int, float] = defaultdict(float)
    
    for term in query_terms:
        if term not in inverted_index:
            continue
            
        postings = inverted_index[term]
        df = len(postings)
        # IDF calculation matching typical BM25 standard formula
        idf = max(0.0, math.log(1.0 + ((doc_count - df + 0.5) / (df + 0.5))))
        
        for doc_index, freq in postings:
            doc_length = doc_lengths[doc_index] or 1
            numerator = freq * (BM25_K1 + 1.0)
            denominator = freq + BM25_K1 * (1.0 - BM25_B + BM25_B * (doc_length / avg_doc_length))
            scores[doc_index] += idf * (numerator / denominator)

    scored: list[tuple[float, float, float, Document]] = []
    
    for doc_index, lexical_score in scores.items():
        doc = corpus[doc_index]
        if allowed_sources and _doc_source(doc).lower() not in allowed_sources:
            continue
            
        # Incorporate heuristic scoring
        heuristic_score, heuristic_boost, page_bias = _document_score(question, doc)
        
        score = lexical_score
        if _is_syllabus_query(question):
            score += heuristic_boost
        else:
            score += heuristic_score * 0.15
            
        if score > 0:
            # Propagate the 'score' property in metadata to assist RRF/hybrid combiner
            doc_with_score = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "score": score}
            )
            scored.append((score, heuristic_boost, page_bias, doc_with_score))

    if not scored:
        filtered = [
            doc for doc in corpus 
            if not allowed_sources or _doc_source(doc).lower() in allowed_sources
        ]
        return filtered[:k]

    # Sort primarily by BM25/hybrid score, then heuristic boost, then page bias
    scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    primary_docs = [doc for _, _, _, doc in scored[:k]]
    
    # Expand neighbor chunks for continuity
    return primary_docs[:max(k, 4)]



_adjacency_map = {}
_adjacency_map_lock = threading.Lock()

def _build_adjacency_map(corpus):
    local_map = {}
    for doc in corpus:
        metadata = doc.metadata or {}
        document_path = metadata.get("document_path")
        page_number = metadata.get("page_number")
        chunk_index = metadata.get("chunk_index")
        if document_path and isinstance(page_number, int) and isinstance(chunk_index, int):
            local_map[(document_path, page_number, chunk_index)] = doc
            
    with _adjacency_map_lock:
        global _adjacency_map
        _adjacency_map = local_map

def _expand_neighbor_chunks(doc: Document, milvus_client, collection_name: str) -> List[Document]:
    """
    Query Milvus for neighboring chunks (i-1 and i+1) based on metadata filtering.
    """
    metadata = doc.metadata or {}
    source = metadata.get("source")
    chunk_index = metadata.get("chunk_index")
    
    # If we don't have enough metadata to find neighbors, return the original doc
    if source is None or chunk_index is None:
        return [doc]
        
    target_indices = [chunk_index - 1, chunk_index + 1]
    target_indices = [i for i in target_indices if i >= 0]
    
    if not target_indices:
        return [doc]
        
    # Escape source string for the Milvus expression
    escaped_source = source.replace("\\", "\\\\").replace('"', '\\"')
    
    # Construct the PyMilvus query expression
    expr = f'source == "{escaped_source}" and chunk_index in {target_indices}'
    
    try:
        # Request all known metadata fields along with the text
        output_fields = ["text"] + list(metadata.keys())
        
        results = milvus_client.query(
            collection_name=collection_name,
            filter=expr,
            output_fields=output_fields
        )
        
        neighbors = []
        for res in results:
            text = res.pop("text", "")
            # Remove Milvus specific fields if they were fetched
            res.pop("pk", None)
            res.pop("vector", None)
            neighbors.append(Document(page_content=text, metadata=res))
            
        # Combine the original document with its neighbors
        all_docs = [doc] + neighbors
        
        # Sort by chunk_index to maintain reading order
        all_docs.sort(key=lambda x: x.metadata.get("chunk_index", 0))
        
        return all_docs
        
    except Exception as e:
        logger.warning("Failed to expand neighbor chunks for %s (index %s): %s", source, chunk_index, e)
        return [doc]




def _preprocess_query(question: str) -> str:
    q = question
    replacements = {
        r'\bcs\b': 'Computer Science',
        r'\bcse\b': 'Computer Science and Engineering',
        r'\bdbms\b': 'Database Management System',
        r'\bml\b': 'Machine Learning',
        r'\bai\b': 'Artificial Intelligence',
        r'\bos\b': 'Operating System',
    }
    for pat, rep in replacements.items():
        q = re.sub(pat, rep, q, flags=re.IGNORECASE)
    return q


def _cross_encoder_rerank(query: str, docs: List[Document], k: int) -> List[Document]:
    """
    Rerank documents using a CrossEncoder model.
    """
    if not docs:
        return []
    
    try:
        model = _get_cross_encoder()
    except ImportError:
        # Fallback if cross-encoder is not available
        return docs[:k]
    
    # Prepare query-document pairs
    pairs = [[query, doc.page_content] for doc in docs]
    
    # Predict scores
    scores = model.predict(pairs)
    
    # Pair up docs and scores, then sort
    scored_docs = list(zip(docs, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True)
    
    # Update metadata with the rerank score and return top k
    reranked_docs = []
    for doc, score in scored_docs[:k]:
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rerank_score"] = float(score)
        reranked_docs.append(doc)
        
    return reranked_docs

def _retrieve_docs(question: str) -> list:
    """
    Main retrieval function orchestrating Concurrent Dense + BM25 search, 
    RRF Fusion, Deduplication, Cross-Encoder Reranking, and Neighbor Expansion.
    """
    logger.info("REQUEST_RECEIVED | request_id=- | query='%s'", question)
    question_processed = _preprocess_query(question)
    k = _compute_dynamic_top_k(question_processed)
    target_sources = _extract_target_sources(question_processed)
    
    if target_sources:
        k = max(k, 6)
        
    search_k = k * 2

    start_time = time.perf_counter()
    
    dense_docs = []
    bm25_docs = []
    
    dense_failed = False
    dense_timeout = False
    
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        dense_future = executor.submit(_dense_search_pipeline, question_processed, search_k, target_sources)
        bm25_future = executor.submit(_search_bm25_fallback, question_processed, search_k, target_sources)
        
        try:
            dense_docs = dense_future.result(timeout=15.0)
        except concurrent.futures.TimeoutError:
            dense_failed = True
            dense_timeout = True
            logger.error("Dense search pipeline timed out (15s)")
        except Exception as e:
            dense_failed = True
            logger.error("Dense search pipeline failed: %s", e)
            
        try:
            bm25_docs = bm25_future.result(timeout=15.0)
        except Exception as e:
            logger.error("BM25 search pipeline failed: %s", e)
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)
            
    concurrent_latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info("CONCURRENT_SEARCH_COMPLETED | latency_ms=%.1f | dense_count=%d | bm25_count=%d", 
                concurrent_latency_ms, len(dense_docs), len(bm25_docs))

    # Detailed retrieval stats logging
    total_retrieval_latency_ms = concurrent_latency_ms
    fallback_triggered = len(dense_docs) == 0 or dense_failed
    logger.info("RETRIEVAL_STATS | total_retrieval_latency_ms=%.1f | timeout_triggered=%s | fallback_triggered=%s",
                total_retrieval_latency_ms, dense_timeout, fallback_triggered)

    # Fusion and deduplication
    fused_docs = _rrf_fuse(dense_docs, bm25_docs, search_k)
    
    if not fused_docs:
        logger.warning("FUSION_EMPTY | No documents returned from dense or bm25.")
        return []

    # Optional: Reranking
    logger.info("RERANK_STARTED | request_id=- | chunk_count=%d", len(fused_docs))
    rerank_start_time = time.perf_counter()
    try:
        reranked_docs = _cross_encoder_rerank(question_processed, fused_docs, k)
        rerank_latency_ms = (time.perf_counter() - rerank_start_time) * 1000
        logger.info("RERANK_COMPLETED | request_id=- | latency_ms=%.1f | chunk_count=%d", rerank_latency_ms, len(reranked_docs))
        
        if reranked_docs:
            return reranked_docs[:max(k, 4)]
        return []
    except Exception as exc:
        logger.warning("RERANK_FAILED | error='%s'", exc)
        return fused_docs[:k]
def _source_index_status() -> list[dict]:
    file_metadata = _collect_pdf_metadata()
    tracked_hashes = _load_tracking_map()
    by_source = {
        item["source"]: {
            "source": item["source"],
            "document_path": item["relative_path"],
            "tracked": tracked_hashes.get(item["relative_path"]) is not None,
            "hash_match": tracked_hashes.get(item["relative_path"]) == item["content_hash"],
            "milvus_chunks": None,
            "milvus_count_error": None,
        }
        for item in file_metadata
    }

    cfg = _get_milvus_config()
    if cfg is None:
        return list(by_source.values())

    try:
        client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=max(3.0, MILVUS_HEALTHCHECK_TIMEOUT_SECONDS))
        for source, status in by_source.items():
            expr = _milvus_source_filter_expr({source})
            if not expr:
                continue
            try:
                rows = client.query(
                    collection_name=cfg["collection"],
                    filter=expr,
                    output_fields=["source"],
                    limit=16384,
                )
                status["milvus_chunks"] = len(rows)
            except Exception as source_exc:
                status["milvus_count_error"] = str(source_exc)
    except Exception as exc:
        error = str(exc)
        for status in by_source.values():
            status["milvus_count_error"] = error

    return list(by_source.values())


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
        "sources": _source_index_status(),
    }


def _format_context(docs, max_chars=4000):
    max_tokens = max_chars // 4
    try:
        import tiktoken
        encoder = tiktoken.get_encoding("cl100k_base")
    except ImportError:
        encoder = None

    formatted = []
    
    if encoder:
        current_tokens = 0
        for doc in docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = doc.page_content
            
            header_tokens = len(encoder.encode(chunk_header))
            content_tokens = len(encoder.encode(content))
            total_chunk_tokens = header_tokens + content_tokens
            
            if current_tokens + total_chunk_tokens > max_tokens:
                remaining_tokens = max_tokens - current_tokens - header_tokens
                if remaining_tokens > 20:
                    encoded = encoder.encode(content)
                    truncated_content = encoder.decode(encoded[:remaining_tokens])
                    # Ensure sentence boundary truncation
                    match = list(re.finditer(r'[.!?]\s+', truncated_content))
                    if match:
                        truncated_content = truncated_content[:match[-1].end()].strip()
                    formatted.append(chunk_header + truncated_content + " ... [TRUNCATED]")
                break
            
            formatted.append(chunk_header + content)
            current_tokens += total_chunk_tokens
            
    else:
        current_chars = 0
        for doc in docs:
            source = (doc.metadata or {}).get('source', 'unknown')
            page = (doc.metadata or {}).get('page_number', 'unknown')
            section = (doc.metadata or {}).get('section_type', 'unknown')
            
            chunk_header = f"[Source: {source} | Page {page} | Section {section}]\n"
            content = doc.page_content
            chunk_text = chunk_header + content
            
            if current_chars + len(chunk_text) > max_chars:
                remaining_chars = max_chars - current_chars
                if remaining_chars > len(chunk_header) + 20:
                    allowed_len = remaining_chars - len(chunk_header)
                    truncated_content = content[:allowed_len]
                    match = list(re.finditer(r'[.!?]\s+', truncated_content))
                    if match:
                        truncated_content = truncated_content[:match[-1].end()].strip()
                    formatted.append(chunk_header + truncated_content + " ... [TRUNCATED]")
                break
                
            formatted.append(chunk_text)
            current_chars += len(chunk_text) + 2
            
    return "\n\n".join(formatted)


def get_retriever():
    store = get_vector_store()
    if not store:
        return None
    return store.as_retriever(search_kwargs={"k": TOP_K})


def _milvus_endpoint_reachable(cfg: dict) -> bool:
    return True

# Fallback cache scheduling removed for strict offline performance.




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
                _ingest_documents_with_client(cfg, embeddings, docs)
                _save_tracking_rows(file_metadata)
                try:
                    vector_store = _build_langchain_vector_store(cfg, embeddings)
                    vector_store.similarity_search("index readiness probe", k=1)
                except Exception as wrapper_exc:
                    logger.warning(
                        "Milvus ingestion succeeded but LangChain wrapper init failed; "
                        "using direct Milvus client retrieval path. Error: %s",
                        wrapper_exc,
                    )
                    _milvus_health["last_error"] = None
                    _milvus_health["unhealthy_until"] = 0.0
                    return None
                logger.info("Milvus vector store operational.")
                _milvus_health["last_error"] = None
                _milvus_health["unhealthy_until"] = 0.0
                return vector_store

        if not should_sync:
            ensure_collection_schema(cfg, embeddings, recreate=False)
            try:
                vector_store = _build_langchain_vector_store(cfg, embeddings)
            except Exception as wrapper_exc:
                logger.warning(
                    "LangChain Milvus wrapper unavailable; using direct Milvus client retrieval path. "
                    "Error: %s",
                    wrapper_exc,
                )
                _milvus_health["last_error"] = None
                _milvus_health["unhealthy_until"] = 0.0
                return None
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


# --- Retrieval Circuit Breaker ---
_cloud_circuit_breaker = {
    "consecutive_failures": 0,
    "bypass_until": 0.0,
}
CLOUD_FAILURE_THRESHOLD = 1
CLOUD_COOLDOWN_SECONDS = 60.0

def _get_deployment_mode() -> str:
    mode = os.getenv("ACADEMERAG_MILVUS_DEPLOYMENT")
    if mode:
        return mode.strip().lower()
    if _env_bool("ACADEMERAG_ENABLE_MILVUS_CLOUD", default=False):
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

def _search_milvus_with_config(cfg: dict, question: str, k: int, target_sources: set[str] | None, timeout_sec: float) -> list[Document]:
    if not cfg:
        return []
    source_expr = _milvus_source_filter_expr(target_sources or set())
    embeddings = OllamaEmbeddings(model=cfg["model"], base_url=OLLAMA_BASE_URL)
    query_vector = embeddings.embed_query(question)
    client = _connect_milvus_client_with_timeout(cfg, timeout_seconds=timeout_sec)
    search_kwargs = {
        "collection_name": cfg["collection"],
        "data": [query_vector],
        "anns_field": "vector",
        "search_params": {"metric_type": "COSINE", "params": {}},
        "limit": k,
        "output_fields": ["text", "source", "document_path", "document_hash", "page_number", "chunk_index"],
        "timeout": timeout_sec,
    }
    if source_expr:
        search_kwargs["filter"] = source_expr
    try:
        rows = client.search(**search_kwargs)
    except Exception as e:
        if "does not exist" in str(e) or "collection" in str(e).lower():
            logger.warning("Milvus collection '%s' does not exist; returning empty list. Error: %s", cfg["collection"], e)
            return []
        raise e
    hits = rows[0] if rows else []
    docs = []
    for hit in hits:
        if isinstance(hit, dict):
            entity = hit.get("entity") or {}
        else:
            entity = getattr(hit, "entity", {}) or {}
        text = str(entity.get("text") or "")
        if not text:
            continue
        metadata = {key: value for key, value in entity.items() if key != "text"}
        docs.append(Document(page_content=text, metadata=metadata))
    return _filter_docs_by_sources(docs, target_sources or set())

def _search_cloud_milvus(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    logger.info("CLOUD_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    
    cfg = _get_cloud_config()
    if not cfg:
        logger.info("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Cloud not configured'", question)
        return []
    
    global _cloud_circuit_breaker
    if time.monotonic() < _cloud_circuit_breaker["bypass_until"]:
        logger.info("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=0.0 | reason='Circuit breaker open'", question)
        logger.info("CIRCUIT_BREAKER_STATE | status='open' | bypass_until=%f", _cloud_circuit_breaker["bypass_until"])
        return []
    else:
        logger.info("CIRCUIT_BREAKER_STATE | status='closed'")

    timeout_sec = 1.5
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _search_milvus_with_config, 
            cfg, question, k, target_sources, timeout_sec
        )
        docs = future.result(timeout=timeout_sec + 1.0)
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info("CLOUD_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d", 
                    question, latency_ms, len(docs))
        _cloud_circuit_breaker["consecutive_failures"] = 0
        return docs
        
    except concurrent.futures.TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("CLOUD_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f", 
                       question, latency_ms)
        _cloud_circuit_breaker["consecutive_failures"] += 1
        if _cloud_circuit_breaker["consecutive_failures"] >= CLOUD_FAILURE_THRESHOLD:
            _cloud_circuit_breaker["bypass_until"] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
            logger.warning("Cloud Milvus circuit breaker OPENED for %.1fs | reason='timeout'", CLOUD_COOLDOWN_SECONDS)
        return []
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("CLOUD_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'", 
                       question, latency_ms, exc)
        _cloud_circuit_breaker["consecutive_failures"] += 1
        if _cloud_circuit_breaker["consecutive_failures"] >= CLOUD_FAILURE_THRESHOLD:
            _cloud_circuit_breaker["bypass_until"] = time.monotonic() + CLOUD_COOLDOWN_SECONDS
            logger.warning("Cloud Milvus circuit breaker OPENED for %.1fs | reason='failure'", CLOUD_COOLDOWN_SECONDS)
        return []
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

def _search_local_milvus(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    logger.info("LOCAL_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    
    cfg = _get_local_config()
    timeout_sec = 3.0
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _search_milvus_with_config, 
            cfg, question, k, target_sources, timeout_sec
        )
        docs = future.result(timeout=timeout_sec + 1.0)
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info("LOCAL_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d", 
                    question, latency_ms, len(docs))
        return docs
        
    except concurrent.futures.TimeoutError:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("LOCAL_SEARCH_TIMEOUT | request_id=- | query='%s' | latency_ms=%.1f", 
                       question, latency_ms)
        return []
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("LOCAL_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'", 
                       question, latency_ms, exc)
        return []
    finally:
        try:
            executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            executor.shutdown(wait=False)

    return []

def _search_bm25_fallback(question: str, k: int, target_sources: set[str] | None) -> list[Document]:
    """
    Wrapper for BM25 retrieval that acts as the sparse leg of the parallel hybrid search.
    """
    logger.info("BM25_SEARCH_STARTED | request_id=- | query='%s'", question)
    start_time = time.perf_counter()
    try:
        docs = _fallback_retrieve_docs(question, k, target_sources=target_sources)
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.info("BM25_SEARCH_COMPLETED | request_id=- | query='%s' | latency_ms=%.1f | chunk_count=%d", question, latency_ms, len(docs))
        return docs
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000
        logger.warning("BM25_SEARCH_FAILED | request_id=- | query='%s' | latency_ms=%.1f | error='%s'", question, latency_ms, exc)
        return []




def _tokenize(text: str) -> list[str]:
    return re.findall('[a-z0-9]+', (text or '').lower())

def _query_keywords(question: str) -> set[str]:
    return {token for token in _tokenize(question) if token not in STOPWORDS}

def _query_subject_phrases(question: str) -> list[str]:
    raw = (question or '').strip()
    if not raw:
        return []
    normalized = re.sub('\\s+', ' ', raw.lower().rstrip('?.!'))
    candidates: list[str] = []
    if 'following subjects' in normalized:
        tail = re.split('following subjects(?:\\s+in\\s+[a-z0-9 &/-]+)?\\s*[:\\-]?', raw, flags=re.IGNORECASE, maxsplit=1)
        subject_block = tail[1] if len(tail) > 1 else raw
        subject_block = re.sub('\\s{2,}', '\n', subject_block)
        for line in subject_block.splitlines():
            phrase = re.sub('^[\\-\\*\\u2022\\d\\.\\)\\(]+\\s*', '', line).strip(' ,;:-')
            if len(phrase) >= 4:
                candidates.append(phrase.lower())
    else:
        matches = list(re.finditer('\\b(?:in|of|for)\\s+([a-z][a-z0-9 &/-]{4,})$', normalized))
        if matches:
            phrase = matches[-1].group(1).strip()
            if ' in ' in phrase:
                phrase = phrase.rsplit(' in ', 1)[-1].strip()
            candidates.append(phrase)
    cleaned: list[str] = []
    seen: set[str] = set()
    for phrase in candidates:
        phrase = re.sub('\\s+', ' ', phrase.strip())
        for prefix in ('course ', 'subject ', 'the course ', 'the subject '):
            if phrase.startswith(prefix):
                phrase = phrase[len(prefix):].strip()
        if len(phrase) < 4:
            continue
        if phrase in {'easwari engineering college', 'the following subjects'}:
            continue
        if phrase not in seen:
            seen.add(phrase)
            cleaned.append(phrase)
    return cleaned

def _query_subject_phrase(question: str) -> str | None:
    phrases = _query_subject_phrases(question)
    if len(phrases) != 1:
        return None
    return phrases[0]

def _is_multi_subject_query(question: str) -> bool:
    phrases = _query_subject_phrases(question)
    return len(phrases) >= 2

def _is_unit_title_query(question: str) -> bool:
    normalized = (question or '').lower()
    return 'unit' in normalized and ('title' in normalized or 'titles' in normalized or 'name' in normalized or ('names' in normalized))

def _is_syllabus_query(question: str) -> bool:
    normalized = (question or '').lower()
    return 'syllabus' in normalized or 'unit' in normalized or 'units' in normalized

def _unit_heading_count(text: str) -> int:
    return len(re.findall('\\bunit\\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\\d+)\\b', (text or '').lower()))

def _explicit_unit_title_line_count(text: str) -> int:
    return len(re.findall('(?im)^\\s*unit\\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\\d+)\\s+[a-z][a-z0-9 ,&()/:-]{3,}$', (text or '').lower()))

def _document_score(question: str, doc: Document) -> tuple[int, int, int]:
    text = doc.page_content or ''
    normalized = text.lower()
    subject_phrases = _query_subject_phrases(question)
    multi_subject = len(subject_phrases) >= 2
    subject_phrase = subject_phrases[0] if len(subject_phrases) == 1 else None
    tokens = Counter(_tokenize(text))
    keyword_score = sum((min(freq, tokens[token]) for token, freq in Counter(_query_keywords(question)).items()))
    boost = 0
    if _is_syllabus_query(question):
        unit_count = _unit_heading_count(text)
        explicit_unit_titles = _explicit_unit_title_line_count(text)
        if explicit_unit_titles:
            boost += explicit_unit_titles * 10
        elif unit_count:
            boost += unit_count
        if 'digital logic design' in normalized:
            boost += 4
        if 'course objectives' in normalized:
            boost -= 4
        if 'program outcomes' in normalized:
            boost -= 4
        if 'assessment methodology' in normalized or 'written test' in normalized:
            boost -= 5
        if subject_phrases:
            matches = sum((1 for phrase in subject_phrases if phrase in normalized))
            if matches:
                boost += 8 * matches
            elif subject_phrase:
                boost -= 20
            elif multi_subject:
                boost -= 1
    page_number = int((doc.metadata or {}).get('page_number') or 0)
    return (keyword_score + boost, boost, -page_number)

def _has_explicit_support(question: str, docs: list[Document]) -> bool:
    if not docs:
        return False
    if _is_syllabus_query(question):
        return any((_explicit_unit_title_line_count(doc.page_content) >= 1 for doc in docs))
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
        key = ((doc.metadata or {}).get('document_path'), (doc.metadata or {}).get('page_number'))
        existing = by_page.get(key)
        if existing is None:
            by_page[key] = doc
            continue
        current_index = int((doc.metadata or {}).get('chunk_index') or 0)
        existing_index = int((existing.metadata or {}).get('chunk_index') or 0)
        if current_index < existing_index:
            by_page[key] = doc
    augmented = list(docs)
    seen = {((doc.metadata or {}).get('document_path'), (doc.metadata or {}).get('page_number'), (doc.metadata or {}).get('chunk_index')) for doc in docs}
    for doc in docs:
        page_number = (doc.metadata or {}).get('page_number')
        document_path = (doc.metadata or {}).get('document_path')
        if not document_path or not isinstance(page_number, int):
            continue
        if _explicit_unit_title_line_count(doc.page_content) < 1:
            continue
        next_doc = by_page.get((document_path, page_number + 1))
        if not next_doc:
            continue
        next_key = ((next_doc.metadata or {}).get('document_path'), (next_doc.metadata or {}).get('page_number'), (next_doc.metadata or {}).get('chunk_index'))
        if next_key not in seen:
            augmented.append(next_doc)
            seen.add(next_key)
    return augmented

@lru_cache(maxsize=1)
def _raw_page_text_map(signature: tuple[tuple[str, str], ...]) -> dict[tuple[str, int], str]:
    pages: dict[tuple[str, int], str] = {}
    file_metadata = _collect_pdf_metadata()
    for item in file_metadata:
        reader = PdfReader(item['path'])
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or '').strip()
            if text:
                pages[item['relative_path'], page_number] = text
    return pages

def _page_text_map() -> dict[tuple[str, int], str]:
    return _raw_page_text_map(_fallback_signature(_collect_pdf_metadata()))

def _is_syllabus_noise_heading(line: str) -> bool:
    normalized = re.sub('\\s+', ' ', (line or '').strip().lower()).rstrip(':')
    if not normalized:
        return False
    return any((normalized.startswith(prefix) for prefix in _SYLLABUS_NOISE_HEADINGS))

def _is_page_header_line(line: str) -> bool:
    normalized = re.sub('\\s+', ' ', (line or '').strip().lower())
    return bool(normalized and (normalized.startswith('directorate of technical education') or normalized.startswith('2023 regulation') or normalized == 'theory 3 0 0 3' or (normalized == 'practicum 1 0 4 3') or (normalized == 'practical 0 0 4 2') or re.fullmatch('\\d+', normalized)))

def _is_syllabus_noise_item(line: str) -> bool:
    stripped = (line or '').strip()
    normalized = stripped.lower()
    if not stripped:
        return True
    if _is_page_header_line(stripped):
        return True
    if re.match('^(?:https?://|www\\.)', normalized):
        return True
    if re.match('^[\\d]+\\s*[\\.\\)]\\s+', stripped):
        return True
    if re.match('^[ΓÇóΓùÅ\\-]\\s*', stripped):
        return True
    if normalized.startswith(('hardware requirement', 'software requirement', 'the following student')):
        return True
    bibliography_markers = ('edition', 'press', 'pearson', 'mc-graw', 'mcgraw', 'wiley', 'springer', 'oxford', 'universities press', 'university press', "o'reilly", 'oreilly', 'publication', 'publications', 'education services', 'pvt. ltd')
    if any((marker in normalized for marker in bibliography_markers)):
        return True
    if re.search('\\b(19|20)\\d{2}\\b', normalized):
        return True
    return False

def _clean_syllabus_text(text: str) -> str:
    lines = [line.rstrip() for line in (text or '').splitlines()]
    cleaned: list[str] = []
    skipping_noise = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if cleaned and cleaned[-1] != '':
                cleaned.append('')
            continue
        if _is_page_header_line(line):
            continue
        if _is_syllabus_noise_heading(line):
            skipping_noise = True
            continue
        if skipping_noise:
            if re.match('(?i)^unit\\s+[ivxlcdm]+\\b', line) or re.match('(?i)^total\\s+(?:hours|periods)\\b', line):
                skipping_noise = False
            elif _is_syllabus_noise_heading(line) or _is_syllabus_noise_item(line):
                continue
            else:
                skipping_noise = False
        if cleaned and cleaned[-1] == '' and (line == ''):
            continue
        cleaned.append(line)
    compacted = '\n'.join(cleaned)
    compacted = re.sub('\\n{3,}', '\n\n', compacted)
    return compacted.strip()

def _generic_retrieval_boost(question: str, doc: Document) -> float:
    text = doc.page_content or ''
    normalized = text.lower()
    subject_phrases = _query_subject_phrases(question)
    subject_phrase = subject_phrases[0] if len(subject_phrases) == 1 else None
    boost = 0.0
    if len(subject_phrases) >= 2:
        phrase_matches = sum((1 for phrase in subject_phrases if phrase in normalized))
        if phrase_matches:
            boost += 1.5 * phrase_matches
    elif subject_phrase:
        if subject_phrase in normalized:
            boost += 3.5
        else:
            boost -= 1.5
    query_text = (question or '').lower()
    if 'lab' in query_text and 'practical' in normalized:
        boost += 1.0
    if 'objective' in query_text and 'course objectives' in normalized:
        boost += 2.0
    if 'experiment' in query_text and ('ex no' in normalized or 'experiment' in normalized):
        boost += 2.0
    if 'syllabus' in query_text and 'total periods' in normalized:
        boost += 0.5
    return boost

def _rrf_fuse(dense_docs: List[Union[Document, Tuple[Document, float]]], 
              sparse_docs: List[Union[Document, Tuple[Document, float]]], 
              k: int) -> List[Document]:
    """
    Combine dense and sparse documents using Reciprocal Rank Fusion.
    score = 1 / (60 + rank)
    Deduplication is performed by (source, page_number, chunk_index).
    """
    def extract_doc(item: Union[Document, Tuple[Document, float]]) -> Document:
        return item[0] if isinstance(item, tuple) else item

    def doc_key(doc: Document) -> Tuple:
        metadata = doc.metadata or {}
        return (
            metadata.get("source"),
            metadata.get("page_number"),
            metadata.get("chunk_index"),
            doc.page_content if metadata.get("chunk_index") is None else None
        )

    rrf_scores = {}
    doc_map = {}

    # Rank and score dense docs
    for rank, item in enumerate(dense_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    # Rank and score sparse docs
    for rank, item in enumerate(sparse_docs):
        doc = extract_doc(item)
        key = doc_key(doc)
        if key not in doc_map:
            doc_map[key] = doc
        rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (60.0 + rank)

    # Sort documents by their RRF score in descending order
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    
    # Retrieve the top k documents and update their metadata with the RRF score
    fused_docs = []
    for key in sorted_keys[:k]:
        doc = doc_map[key]
        if doc.metadata is None:
            doc.metadata = {}
        doc.metadata["rrf_score"] = rrf_scores[key]
        fused_docs.append(doc)

    return fused_docs

def _get_cross_encoder():
    """Lazy-load the CrossEncoder model."""
    global _cross_encoder_model
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                logger.info("Initializing CrossEncoder model for reranking...")
                try:
                    from sentence_transformers import CrossEncoder
                    # Standard efficient cross-encoder model
                    _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                except ImportError:
                    logger.error("sentence_transformers is not installed. CrossEncoder reranking will fail.")
                    raise
    return _cross_encoder_model

def preload_cross_encoder():
    """Eagerly load the CrossEncoder model to avoid lazy-loading on first request."""
    try:
        _get_cross_encoder()
    except Exception as exc:
        logger.warning("Failed to preload CrossEncoder: %s", exc)

def _dense_search_pipeline(question: str, k: int, target_sources: Optional[Set[str]]) -> list:
    """
    Tries Milvus Cloud first, falls back to local Milvus if Cloud returns no results or fails.
    """
    start_time = time.perf_counter()
    docs = _search_cloud_milvus(question, k, target_sources)
    fallback_used = False
    
    if not docs:
        docs = _search_local_milvus(question, k, target_sources)
        fallback_used = True
    
    latency_ms = (time.perf_counter() - start_time) * 1000
    logger.info("DENSE_PIPELINE_COMPLETED | query='%s' | latency_ms=%.1f | chunk_count=%d | fallback_used=%s", 
                question, latency_ms, len(docs), fallback_used)
    return docs

# Pre-build BM25 strictly at startup
_init_bm25_index_at_startup()
