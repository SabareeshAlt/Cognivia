"""
database/chunking.py
--------------------
PDF loading, text extraction via sandbox, section-aware chunking,
and page-text map utilities.
"""

import logging
import os
import re
import time
from functools import lru_cache

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from database.config import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

try:
    import magic
    magic.from_file(__file__)
except Exception:
    import sys
    from types import ModuleType
    _dummy = ModuleType("magic")
    def _from_file(filename, mime=False):
        import mimetypes
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"
    _dummy.from_file = _from_file
    sys.modules["magic"] = _dummy
    import magic


def _load_and_chunk_files(file_metadata: list[dict]) -> list[Document]:
    """
    Load PDF files, extract text via sandbox, and chunk using
    RecursiveCharacterTextSplitter with section-aware boundary tracking.
    """
    from rag.pdf_sandbox import extract_pdf_text_sandboxed

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", " ", ""],
    )
    all_chunks = []
    logger.info("Starting structure-aware parse/chunk stage for %s file(s).", len(file_metadata))

    section_pattern = re.compile(
        r'(?i)^(UNIT\s+[IVXLCDM\d]+.*?|COURSE OBJECTIVES|OUTCOMES|REFERENCES|LAB|ASSESSMENT|PRACTICAL)\s*$'
    )

    for item in file_metadata:
        logger.info("Parsing file: %s", item["relative_path"])
        path = item["path"]

        # Validate PDF magic bytes
        with open(path, 'rb') as f:
            header = f.read(5)
            if header != b'%PDF-':
                logger.error(
                    "Invalid file signature for %s. Expected '%%PDF-'. Skipping.",
                    item['relative_path']
                )
                continue

        # Validate MIME type
        mime = magic.from_file(path, mime=True)
        if mime != 'application/pdf':
            logger.error(
                "Invalid MIME type '%s' for %s. Expected 'application/pdf'. Skipping.",
                mime, item['relative_path']
            )
            continue

        try:
            pages = extract_pdf_text_sandboxed(path, timeout=180)
        except Exception as e:
            logger.error("Sandbox extraction failed for %s: %s. Skipping.", item['relative_path'], e)
            continue

        page_count = len(pages)
        current_subject = item["source"].replace('.pdf', '')
        current_unit_number = None
        current_unit_title = None
        current_section_type = "GENERAL"
        current_section_text = ""
        page_boundaries: list[tuple[int, int]] = []
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
                        "file_name": item["source"],
                        "relative_path": item["relative_path"],
                        "absolute_path": os.path.abspath(path),
                        "chunk_id": f"{item['source']}_{chunk_index}",
                        "document_id": item["content_hash"],
                        "file_hash": item["content_hash"],
                        "ingestion_timestamp": int(time.time()),
                        "source_type": "pdf",
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

            if not page_boundaries or page_boundaries[-1][0] < len(current_section_text):
                page_boundaries.append((len(current_section_text), idx))
            elif page_boundaries:
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
                    page_boundaries.append((len(current_section_text), idx))
                    current_section_text += line + "\n"
                else:
                    current_section_text += line + "\n"

            if idx % 10 == 0 or idx == page_count:
                logger.info("  %s page(s) processed for %s", idx, item["source"])

        flush_section()

    return all_chunks


def _fallback_signature(file_metadata: list[dict]) -> tuple[tuple[str, str], ...]:
    """Return a stable signature tuple from file metadata for cache keys."""
    return tuple((item["relative_path"], item["content_hash"]) for item in file_metadata)


@lru_cache(maxsize=1)
def _raw_page_text_map(signature: tuple[tuple[str, str], ...]) -> dict[tuple[str, int], str]:
    from database.ingestion import _collect_pdf_metadata
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
    from database.ingestion import _collect_pdf_metadata
    from database.chunking import _fallback_signature as _sig
    return _raw_page_text_map(_sig(_collect_pdf_metadata()))
