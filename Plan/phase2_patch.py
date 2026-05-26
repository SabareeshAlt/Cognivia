import re
import sys

def apply_phase2_patch():
    with open("Milvus.py", "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Query preprocessing
    query_pre_code = r"""
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
"""
    # Insert before _retrieve_docs
    content = content.replace("def _retrieve_docs(question: str) -> list[Document]:", query_pre_code + "\ndef _retrieve_docs(question: str) -> list[Document]:")

    # 2. Structure-aware chunking and Metadata enrichment
    new_chunking = r"""def _load_and_chunk_files(file_metadata: list[dict]) -> list[Document]:
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
        
        chunk_index = 0
        for idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue
                
            lines = page_text.split('\n')
            current_buffer = []
            
            def flush_buffer():
                nonlocal chunk_index, current_buffer
                text_to_chunk = "\n".join(current_buffer)
                if text_to_chunk.strip():
                    chunks = splitter.split_text(text_to_chunk)
                    for c in chunks:
                        all_chunks.append(Document(
                            page_content=c,
                            metadata={
                                "source": item["source"],
                                "subject_name": current_subject,
                                "document_path": item["relative_path"],
                                "document_hash": item["content_hash"],
                                "page_number": idx,
                                "unit_number": current_unit_number,
                                "unit_title": current_unit_title,
                                "section_type": current_section_type,
                                "chunk_index": chunk_index,
                            }
                        ))
                        chunk_index += 1
                current_buffer = []

            for line in lines:
                match = section_pattern.match(line.strip())
                if match:
                    flush_buffer()
                    heading = match.group(1).upper()
                    if heading.startswith("UNIT"):
                        current_section_type = "UNIT"
                        parts = heading.split(maxsplit=2)
                        current_unit_number = parts[1] if len(parts) > 1 else None
                        current_unit_title = heading
                    else:
                        current_section_type = heading
                    current_buffer.append(line)
                else:
                    current_buffer.append(line)
            flush_buffer()
            
            if idx % 10 == 0 or idx == page_count:
                logger.info("  %s page(s) processed for %s", idx, item["source"])
                
    return all_chunks"""
    
    content = re.sub(r'def _load_and_chunk_files\(file_metadata: list\[dict\]\) -> list\[Document\]:.*?(?=\ndef _ingest_documents_in_batches)', lambda m: new_chunking, content, flags=re.DOTALL)

    # 3. Reranking
    rerank_code = r"""
def _cross_encoder_rerank(query: str, docs: list[Document], top_k: int) -> list[Document]:
    if not docs:
        return docs
    try:
        from sentence_transformers import CrossEncoder
        encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        pairs = [[query, doc.page_content] for doc in docs]
        scores = encoder.predict(pairs)
        scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, score in scored_docs[:top_k]]
    except ImportError:
        logger.warning("sentence_transformers not installed. Skipping cross-encoder reranking.")
        return docs[:top_k]
"""
    content = content.replace("def _retrieve_docs(question: str) -> list[Document]:", rerank_code + "\ndef _retrieve_docs(question: str) -> list[Document]:")

    # 4. Hybrid Search + RRF
    hybrid_search_logic = r"""def _retrieve_docs(question: str) -> list[Document]:
    question = _preprocess_query(question)
    k = _compute_dynamic_top_k(question)
    target_sources = _extract_target_sources(question)
    source_expr = _milvus_source_filter_expr(target_sources)
    if target_sources:
        k = max(k, 6)
        
    store = get_vector_store()
    vector_docs = []
    if store:
        try:
            if source_expr:
                scored = store.similarity_search_with_relevance_scores(question, k=k*2, expr=source_expr)
            else:
                scored = store.similarity_search_with_relevance_scores(question, k=k*2)
            vector_docs = [doc for doc, score in scored]
        except Exception as exc:
            logger.warning("Milvus vector search failed: %s", exc)
            
    bm25_docs = _fallback_retrieve_docs(question, k*2, target_sources=target_sources)
    
    # RRF Merge
    rrf_scores = {}
    doc_map = {}
    
    for rank, doc in enumerate(vector_docs):
        doc_hash = hash(doc.page_content)
        doc_map[doc_hash] = doc
        rrf_scores[doc_hash] = rrf_scores.get(doc_hash, 0.0) + 1.0 / (60.0 + rank + 1)
        
    for rank, doc in enumerate(bm25_docs):
        doc_hash = hash(doc.page_content)
        doc_map[doc_hash] = doc
        rrf_scores[doc_hash] = rrf_scores.get(doc_hash, 0.0) + 1.0 / (60.0 + rank + 1)
        
    sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    merged_docs = [doc_map[h] for h, score in sorted_docs][:k*2]
    
    # Deduplicate chunks
    final_docs = []
    seen_content = set()
    for doc in merged_docs:
        if doc.page_content not in seen_content:
            seen_content.add(doc.page_content)
            final_docs.append(doc)
            
    # Reranking
    reranked_docs = _cross_encoder_rerank(question, final_docs, k)
    
    if reranked_docs:
        return _expand_neighbor_chunks(reranked_docs, max_docs=max(k, 4), allowed_sources=target_sources)
    return []"""
    
    content = re.sub(r'def _retrieve_docs\(question: str\) -> list\[Document\]:.*?(?=\ndef _source_index_status)', lambda m: hybrid_search_logic, content, flags=re.DOTALL)

    with open("Milvus.py", "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    apply_phase2_patch()
    print("Phase 2 patch applied successfully.")
