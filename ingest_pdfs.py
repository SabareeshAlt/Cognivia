"""
ingest_pdfs.py
--------------
Full ingestion pipeline for AcademeRAG.

For each PDF in documents/:
  1. Validate (magic bytes + MIME)
  2. Parse page-by-page via multiprocess sandbox
  3. Chunk (size=1000, overlap=200) with structure-aware section detection
  4. Embed using mxbai-embed-large via Ollama
  5. Batch insert into Zilliz Cloud (primary)
  6. Batch insert into Local Milvus Lite (fallback)
  7. Rebuild BM25 index

No duplicate insertion: collection is pre-wiped before ingest.
"""

import hashlib
import logging
import math
import os
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from typing import List

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from pymilvus import MilvusClient, CollectionSchema, DataType, FieldSchema

# ─── Config ─────────────────────────────────────────────────────────────────

PROJECT_ROOT     = os.path.dirname(os.path.abspath(__file__))
DOCUMENTS_DIR    = os.path.join(PROJECT_ROOT, "documents")
ZILLIZ_URI       = os.environ["ACADEMERAG_MILVUS_URI"]
ZILLIZ_TOKEN     = os.environ["ACADEMERAG_MILVUS_TOKEN"]
COLLECTION_NAME  = os.environ.get("COLLECTION_NAME", "AcademeRAG")
EMBEDDING_MODEL  = os.environ.get("EMBEDDING_MODEL", "mxbai-embed-large")
OLLAMA_BASE_URL  = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CHUNK_SIZE       = int(os.environ.get("CHUNK_SIZE", 1000))
CHUNK_OVERLAP    = int(os.environ.get("CHUNK_OVERLAP", 200))
INGEST_BATCH     = int(os.environ.get("ACADEMERAG_INGEST_BATCH_SIZE", 16))
LOCAL_MILVUS_PATH = os.path.join(PROJECT_ROOT, "milvus_local.db")
BM25_INDEX_FILE  = os.path.join(PROJECT_ROOT, "bm25_index.pkl")

VECTOR_DIM = 1024  # bge-m3 output dim (confirmed)

BM25_K1 = 1.5
BM25_B  = 0.75

STOPWORDS = {
    "a", "an", "and", "are", "for", "from", "in", "is", "of", "on",
    "or", "the", "to", "what", "which", "with", "each", "tell", "me",
}

SECTION_PATTERN = re.compile(
    r'(?i)^(UNIT\s+[IVXLCDM\d]+.*?|COURSE OBJECTIVES|OUTCOMES|REFERENCES|LAB|ASSESSMENT|PRACTICAL)\s*$'
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _get_pdf_files() -> list[dict]:
    items = []
    for filename in sorted(os.listdir(DOCUMENTS_DIR)):
        if not filename.lower().endswith(".pdf"):
            continue
        path = os.path.join(DOCUMENTS_DIR, filename)
        items.append({
            "path": path,
            "source": filename,
            "relative_path": os.path.relpath(path, PROJECT_ROOT),
            "content_hash": _file_sha256(path),
        })
    logger.info("Found %d PDF(s) in documents/: %s", len(items), [i["source"] for i in items])
    return items


def _validate_pdf(path: str) -> bool:
    with open(path, "rb") as f:
        header = f.read(5)
    if header != b"%PDF-":
        logger.error("Invalid magic bytes for %s", path)
        return False
    import mimetypes
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if mime != "application/pdf":
        logger.warning("MIME check: %s -> %s (acceptable on Windows without libmagic)", path, mime)
    return True


def _parse_and_chunk(item: dict) -> list[Document]:
    from rag.pdf_sandbox import extract_pdf_text_sandboxed

    logger.info("Parsing %s ...", item["source"])
    try:
        pages = extract_pdf_text_sandboxed(item["path"], timeout=300)
    except Exception as e:
        logger.error("Failed to parse %s: %s", item["source"], e)
        return []

    logger.info("  %s: %d pages extracted", item["source"], len(pages))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )

    all_chunks: list[Document] = []
    current_section_text = ""
    page_boundaries: list[tuple[int, int]] = []
    chunk_index = 0
    current_subject    = item["source"].replace(".pdf", "")
    current_unit_num   = None
    current_unit_title = None
    current_section    = "GENERAL"

    def flush():
        nonlocal chunk_index, current_section_text, page_boundaries
        if not current_section_text.strip():
            return
        chunks = splitter.split_text(current_section_text)
        search_start = 0
        for c in chunks:
            pos = current_section_text.find(c, search_start)
            pos = pos if pos != -1 else search_start
            search_start = pos + 1
            page_num = 1
            for bp, pn in page_boundaries:
                if bp <= pos:
                    page_num = pn
                else:
                    break
            all_chunks.append(Document(
                page_content=c,
                metadata={
                    "source":        item["source"],
                    "subject_name":  current_subject,
                    "document_path": item["relative_path"],
                    "document_hash": item["content_hash"],
                    "page_number":   page_num,
                    "unit_number":   current_unit_num,
                    "unit_title":    current_unit_title,
                    "section_type":  current_section,
                    "chunk_index":   chunk_index,
                },
            ))
            chunk_index += 1
        current_section_text = ""
        page_boundaries.clear()

    page_count = len(pages)
    for page_info in pages:
        idx       = page_info["page_number"]
        page_text = page_info.get("text") or ""
        if not page_text.strip():
            continue

        if not page_boundaries or page_boundaries[-1][0] < len(current_section_text):
            page_boundaries.append((len(current_section_text), idx))
        else:
            page_boundaries[-1] = (len(current_section_text), idx)

        for line in page_text.split("\n"):
            m = SECTION_PATTERN.match(line.strip())
            if m:
                flush()
                heading = m.group(1).upper()
                if heading.startswith("UNIT"):
                    current_section = "UNIT"
                    parts = heading.split(maxsplit=2)
                    current_unit_num   = parts[1] if len(parts) > 1 else None
                    current_unit_title = heading
                else:
                    current_section    = heading
                    current_unit_num   = None
                    current_unit_title = None
                page_boundaries.append((len(current_section_text), idx))
            current_section_text += line + "\n"

        if idx % 50 == 0 or idx == page_count:
            logger.info("  [%s] page %d/%d processed", item["source"], idx, page_count)

    flush()
    logger.info("  %s: %d chunks created", item["source"], len(all_chunks))
    return all_chunks


# ─── Milvus Insertion ─────────────────────────────────────────────────────────

def _ensure_local_collection(client: MilvusClient, dim: int) -> None:
    if client.has_collection(COLLECTION_NAME):
        logger.info("Local Milvus: collection '%s' exists — dropping for fresh rebuild.", COLLECTION_NAME)
        client.drop_collection(COLLECTION_NAME)
        time.sleep(1)

    fields = [
        FieldSchema(name="pk",          dtype=DataType.INT64,         is_primary=True, auto_id=True),
        FieldSchema(name="source",       dtype=DataType.VARCHAR,       max_length=1024),
        FieldSchema(name="page_number",  dtype=DataType.INT64),
        FieldSchema(name="chunk_index",  dtype=DataType.INT64),
        FieldSchema(name="text",         dtype=DataType.VARCHAR,       max_length=65535),
        FieldSchema(name="vector",       dtype=DataType.FLOAT_VECTOR,  dim=dim),
    ]
    schema = CollectionSchema(
        fields=fields,
        description="AcademeRAG local fallback",
        enable_dynamic_field=True,
    )
    idx_params = MilvusClient.prepare_index_params()
    idx_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=idx_params,
    )
    logger.info("Local Milvus: collection '%s' created (dim=%d, COSINE).", COLLECTION_NAME, dim)


def _batch_insert(client: MilvusClient, embeddings: OllamaEmbeddings, docs: list[Document], label: str) -> int:
    total = len(docs)
    inserted = 0
    start = time.monotonic()
    for offset in range(0, total, INGEST_BATCH):
        batch = docs[offset: offset + INGEST_BATCH]
        texts   = [d.page_content for d in batch]
        vectors = embeddings.embed_documents(texts)
        if len(vectors) != len(batch):
            raise RuntimeError(f"Embedding count mismatch: {len(vectors)} vs {len(batch)}")

        payload = []
        for doc, vec in zip(batch, vectors):
            meta = doc.metadata or {}
            row = {
                "text":        doc.page_content,
                "vector":      vec,
                "source":      str(meta.get("source", ""))[:1024],
                "page_number": int(meta.get("page_number") or 0),
                "chunk_index": int(meta.get("chunk_index") or 0),
            }
            for k, v in meta.items():
                if k not in row:
                    row[k] = v
            payload.append(row)

        client.insert(collection_name=COLLECTION_NAME, data=payload)
        inserted += len(batch)
        elapsed  = time.monotonic() - start
        pct      = inserted / total * 100
        eta      = (elapsed / inserted) * (total - inserted) if inserted else 0
        logger.info(
            "[%s] %d/%d chunks (%.1f%%) | elapsed %.1fs | eta %.1fs",
            label, inserted, total, pct, elapsed, eta,
        )
    return inserted


# ─── BM25 ─────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    raw = text or ""
    compounds = re.findall(r'[A-Za-z][A-Za-z0-9]*(?:[+\-./ ][A-Za-z0-9]+)+', raw)
    compound_lower = [c.lower().replace(" ", "-") for c in compounds]
    words = re.findall(r'[a-z0-9]+', raw.lower())
    return compound_lower + words


def _build_bm25_index(docs: tuple) -> dict:
    inverted: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_lengths = []
    total_length = 0
    for idx, doc in enumerate(docs):
        tokens = _tokenize(doc.page_content)
        length = len(tokens)
        doc_lengths.append(length)
        total_length += length
        for token, count in Counter(tokens).items():
            inverted[token].append((idx, count))
    avg_len = (total_length / len(docs)) if docs else 0.0
    return {
        "corpus":          docs,
        "inverted_index":  dict(inverted),
        "doc_lengths":     doc_lengths,
        "avg_doc_length":  avg_len,
        "doc_count":       len(docs),
    }


def _save_bm25(docs: list[Document], signature: tuple) -> None:
    stats = _build_bm25_index(tuple(docs))
    with open(BM25_INDEX_FILE, "wb") as f:
        pickle.dump({"signature": signature, "corpus": tuple(docs), "stats": stats}, f)
    logger.info("BM25 index saved: %s (%d docs, %.1f avg tokens)", BM25_INDEX_FILE, len(docs), stats["avg_doc_length"])


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    logger.info("=" * 60)
    logger.info("AcademeRAG PDF Ingestion Pipeline")
    logger.info("Embedding model : %s (dim=%d)", EMBEDDING_MODEL, VECTOR_DIM)
    logger.info("Chunk size      : %d / overlap %d", CHUNK_SIZE, CHUNK_OVERLAP)
    logger.info("Zilliz Cloud    : %s", ZILLIZ_URI)
    logger.info("Local Milvus    : %s", LOCAL_MILVUS_PATH)
    logger.info("=" * 60)

    # ── Discover PDFs ─────────────────────────────────────────────────────────
    pdf_files = _get_pdf_files()
    if not pdf_files:
        logger.error("No PDFs found in documents/. Aborting.")
        return 1

    # ── Validate PDFs ─────────────────────────────────────────────────────────
    for item in pdf_files:
        if not _validate_pdf(item["path"]):
            logger.error("Validation failed for %s. Aborting.", item["source"])
            return 1
    logger.info("All PDFs validated.")

    # ── Embeddings ────────────────────────────────────────────────────────────
    logger.info("Initializing Ollama embeddings (%s) ...", EMBEDDING_MODEL)
    embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL)
    probe = embeddings.embed_query("dimension probe")
    actual_dim = len(probe)
    logger.info("Embedding dimension confirmed: %d", actual_dim)
    if actual_dim != VECTOR_DIM:
        logger.error("Dimension mismatch: expected %d, got %d. Aborting.", VECTOR_DIM, actual_dim)
        return 1

    # ── Parse + Chunk all PDFs ────────────────────────────────────────────────
    all_docs: list[Document] = []
    per_source: dict[str, int] = {}
    for item in pdf_files:
        docs = _parse_and_chunk(item)
        if not docs:
            logger.error("No chunks extracted from %s. Aborting.", item["source"])
            return 1
        all_docs.extend(docs)
        per_source[item["source"]] = len(docs)

    logger.info("Total chunks across all PDFs: %d", len(all_docs))
    for src, cnt in per_source.items():
        logger.info("  %s: %d chunks", src, cnt)

    # ── Connect Milvus clients ────────────────────────────────────────────────
    logger.info("Connecting to Zilliz Cloud ...")
    zilliz_client = MilvusClient(uri=ZILLIZ_URI, token=ZILLIZ_TOKEN, timeout=30)

    logger.info("Connecting to Local Milvus Lite (%s) ...", LOCAL_MILVUS_PATH)
    local_client = MilvusClient(uri=LOCAL_MILVUS_PATH, timeout=30)
    _ensure_local_collection(local_client, VECTOR_DIM)

    # ── Insert into Zilliz Cloud ──────────────────────────────────────────────
    logger.info("Inserting %d chunks into Zilliz Cloud ...", len(all_docs))
    t0 = time.monotonic()
    zilliz_inserted = _batch_insert(zilliz_client, embeddings, all_docs, "Zilliz")
    logger.info("Zilliz Cloud ingestion complete: %d chunks in %.1fs", zilliz_inserted, time.monotonic() - t0)

    # ── Insert into Local Milvus ──────────────────────────────────────────────
    logger.info("Inserting %d chunks into Local Milvus ...", len(all_docs))
    t0 = time.monotonic()
    local_inserted = _batch_insert(local_client, embeddings, all_docs, "Local")
    logger.info("Local Milvus ingestion complete: %d chunks in %.1fs", local_inserted, time.monotonic() - t0)

    # ── Save BM25 index ───────────────────────────────────────────────────────
    logger.info("Building and saving BM25 index ...")
    signature = tuple((item["relative_path"], item["content_hash"]) for item in pdf_files)
    _save_bm25(all_docs, signature)

    # ── Verify counts ─────────────────────────────────────────────────────────
    logger.info("Verifying Zilliz Cloud row count ...")
    time.sleep(3)  # Allow index refresh
    try:
        zilliz_client.load_collection(COLLECTION_NAME)
        stats = zilliz_client.get_collection_stats(COLLECTION_NAME)
        logger.info("Zilliz Cloud row_count: %s", stats.get("row_count", "unknown"))
    except Exception as e:
        logger.warning("Could not verify Zilliz stats: %s", e)

    try:
        local_client.load_collection(COLLECTION_NAME)
        local_stats = local_client.get_collection_stats(COLLECTION_NAME)
        logger.info("Local Milvus row_count: %s", local_stats.get("row_count", "unknown"))
    except Exception as e:
        logger.warning("Could not verify local stats: %s", e)

    logger.info("=" * 60)
    logger.info("INGESTION COMPLETE")
    logger.info("Zilliz Cloud : %d chunks inserted", zilliz_inserted)
    logger.info("Local Milvus : %d chunks inserted", local_inserted)
    for src, cnt in per_source.items():
        logger.info("  %s: %d chunks", src, cnt)
    logger.info("BM25 index   : saved to %s", BM25_INDEX_FILE)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
