import hashlib
import logging
import os
import re
import time
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

os.environ["MILVUS_ASYNC"] = "0"

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, "documents")
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

INSUFFICIENT_CONTEXT_MESSAGE = (
    "I am not trained on this data source or the uploaded documents do not contain this information."
)


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
TOP_K = _env_int("ACADEMERAG_TOP_K", 3)
DYNAMIC_TOP_K_MIN = _env_int("ACADEMERAG_TOP_K_MIN", 2)
DYNAMIC_TOP_K_MAX = _env_int("ACADEMERAG_TOP_K_MAX", 6)
RELEVANCE_SCORE_THRESHOLD = _env_float("ACADEMERAG_SCORE_THRESHOLD", 0.35)
CHUNK_SIZE = _env_int("CHUNK_SIZE", 1000)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 200)
MILVUS_TIMEOUT_SECONDS = _env_float("ACADEMERAG_MILVUS_TIMEOUT_SECONDS", 15.0)
INGEST_BATCH_SIZE = _env_int("ACADEMERAG_INGEST_BATCH_SIZE", 16)
INGEST_MAX_SECONDS = _env_float("ACADEMERAG_INGEST_MAX_SECONDS", 1800.0)


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
        text_parts = []
        page_count = len(reader.pages)
        for idx, page in enumerate(reader.pages, start=1):
            text_parts.append(page.extract_text() or "")
            if idx % 10 == 0 or idx == page_count:
                logger.info("  %s page(s) processed for %s", idx, item["source"])
        text = "".join(text_parts)
        if not text.strip():
            logger.warning("Skipping %s because no text was extracted.", item["source"])
            continue
        chunks = splitter.split_text(text)
        logger.info(
            "Chunked %s into %s chunk(s) in %.1fs",
            item["source"],
            len(chunks),
            time.monotonic() - file_start,
        )
        for idx, chunk in enumerate(chunks):
            all_chunks.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "source": item["source"],
                        "document_path": item["relative_path"],
                        "document_hash": item["content_hash"],
                        "chunk_index": idx,
                    },
                )
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
    return True


def _milvus_cloud_ready() -> bool:
    return _get_milvus_config() is not None


def initialize_vector_store(force_reindex: bool = False, recreate_collection_on_sync: bool = True):
    cfg = _get_milvus_config()
    if cfg is None:
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
            docs = _load_and_chunk_files(file_metadata)
            if not docs:
                logger.error("No chunkable PDF content found; cannot build vector index.")
                return None
            logger.info("Rebuilding Milvus collection due to sync reason: %s", reason)
            ensure_collection_schema(cfg, embeddings, recreate=recreate_collection_on_sync)
            vector_store = Milvus(
                collection_name=cfg["collection"],
                embedding_function=embeddings,
                connection_args=conn_args,
                auto_id=True,
                primary_field="pk",
                text_field="text",
                vector_field="vector",
                enable_dynamic_field=True,
                timeout=MILVUS_TIMEOUT_SECONDS,
            )
            _ingest_documents_in_batches(vector_store, docs)
            _save_tracking_rows(file_metadata)
        else:
            ensure_collection_schema(cfg, embeddings, recreate=False)
            vector_store = Milvus(
                collection_name=cfg["collection"],
                embedding_function=embeddings,
                connection_args=conn_args,
                primary_field="pk",
                text_field="text",
                vector_field="vector",
                enable_dynamic_field=True,
                timeout=MILVUS_TIMEOUT_SECONDS,
            )
            if reason == "unchanged":
                logger.info("Milvus index unchanged; using existing collection.")
            elif not auto_sync:
                logger.info("Milvus index auto-sync disabled; using existing collection.")

        vector_store.similarity_search("index readiness probe", k=1)
        logger.info("Milvus vector store operational.")
        return vector_store
    except Exception as exc:
        logger.error("Error initializing vector store: %s", exc)
        return None


@lru_cache(maxsize=1)
def get_vector_store():
    store = initialize_vector_store(force_reindex=False)
    if store:
        return store
    if _milvus_cloud_ready():
        logger.error("Failed to create vector store")
    return None


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


@lru_cache(maxsize=1)
def _fallback_chunk_corpus() -> tuple[Document, ...]:
    metadata = _collect_pdf_metadata()
    if not metadata:
        logger.warning("Fallback retrieval unavailable: no PDF documents found.")
        return tuple()
    docs = _load_and_chunk_files(metadata)
    return tuple(docs)


def _fallback_retrieve_docs(question: str, k: int) -> list[Document]:
    corpus = _fallback_chunk_corpus()
    if not corpus:
        return []

    query_tokens = _tokenize(question)
    if not query_tokens:
        return list(corpus[:k])
    query_tf = Counter(query_tokens)

    scored = []
    for doc in corpus:
        doc_tokens = _tokenize(doc.page_content)
        if not doc_tokens:
            continue
        doc_tf = Counter(doc_tokens)
        score = sum(min(freq, doc_tf[token]) for token, freq in query_tf.items())
        if score > 0:
            scored.append((score, doc))

    if not scored:
        return list(corpus[:k])
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:k]]


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
    llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=LLM_TEMPERATURE)
    prompt = ChatPromptTemplate.from_template(
        """
You are an intelligent College AI Assistant.
Answer purely based on the context below.

Context:
{context}

Question:
{question}

Answer:
"""
    )
    return prompt | llm | StrOutputParser()


def get_optimized_response(question: str) -> str:
    docs = _retrieve_docs(question)
    if not docs:
        return INSUFFICIENT_CONTEXT_MESSAGE
    context = "\n\n".join(doc.page_content for doc in docs)
    chain = _build_qa_chain()
    return chain.invoke({"context": context, "question": question})


def stream_optimized_response(question: str):
    docs = _retrieve_docs(question)
    if not docs:
        yield INSUFFICIENT_CONTEXT_MESSAGE
        return
    context = "\n\n".join(doc.page_content for doc in docs)
    chain = _build_qa_chain()
    for chunk in chain.stream({"context": context, "question": question}):
        yield chunk
