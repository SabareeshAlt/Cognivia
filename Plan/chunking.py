import os
import re
import time
import logging
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Constants as requested
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

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
        reader = PdfReader(item["path"])
        page_count = len(reader.pages)
        
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

        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
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
