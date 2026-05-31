"""
diagnose_chunk.py
Find the chunk(s) that cause the mxbai-embed-large context length error.
Re-parse both PDFs, rebuild chunks, then find chunks whose embed fails.
"""
import os, sys, logging, requests
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_pdfs import _get_pdf_files, _validate_pdf, _parse_and_chunk

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "mxbai-embed-large")

def embed_one(text: str) -> bool:
    """Try to embed a single text. Return True if OK, False if over context."""
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/embed",
        json={"model": EMBEDDING_MODEL, "input": text, "truncate": False},
        timeout=30,
    )
    if r.status_code == 400 and "context" in r.text.lower():
        return False
    r.raise_for_status()
    return True

def count_tokens_approx(text: str) -> int:
    """Rough token count estimate via Ollama tokenize."""
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/tokenize",
            json={"model": EMBEDDING_MODEL, "prompt": text},
            timeout=30,
        )
        if r.status_code == 200:
            return len(r.json().get("tokens", []))
    except Exception:
        pass
    return len(text.split()) * 2  # rough fallback

pdf_files = _get_pdf_files()
all_docs = []
for item in pdf_files:
    _validate_pdf(item["path"])
    docs = _parse_and_chunk(item)
    all_docs.extend(docs)

logger.info("Total chunks: %d", len(all_docs))
logger.info("Scanning chunks 5300-5330 for the problem chunk...")

bad_chunks = []
for i, doc in enumerate(all_docs):
    if i < 5300:
        continue
    if i > 5340:
        break
    text = doc.page_content
    toks = count_tokens_approx(text)
    ok = embed_one(text[:1800])
    status = "OK" if ok else "FAIL"
    logger.info(
        "Chunk %d | chars=%d | approx_tokens=%d | source=%s | page=%s | status=%s",
        i, len(text), toks,
        doc.metadata.get("source"), doc.metadata.get("page_number"), status
    )
    if not ok:
        bad_chunks.append((i, text))

logger.info("Bad chunks found: %d", len(bad_chunks))
for i, text in bad_chunks:
    logger.info("  Chunk %d first 200 chars: %r", i, text[:200])
    for limit in [1000, 800, 600, 400, 200]:
        ok = embed_one(text[:limit])
        logger.info("    truncate to %d chars -> %s", limit, "OK" if ok else "FAIL")
