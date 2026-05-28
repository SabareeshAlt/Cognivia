# Context Packing and Token Truncation Audit Report

## 1. Current Implementation
The current RAG pipeline (specifically `llm_orchestration.py` and `Milvus.py`) exhibits several critical flaws in how retrieved context is processed before being sent to the LLM. 

- **Retrieval**: `_retrieve_docs` fetches chunks using concurrent Dense and BM25 searches, fuses them with RRF, and applies a Cross-Encoder for reranking.
- **Augmentation**: `_augment_docs_for_syllabus` appends subsequent chunks (chunk N+1) to the end of the retrieved list for syllabus-specific queries.
- **Formatting**: `_format_context` loops through the retrieved documents, prepends a metadata header, and concatenates them. It enforces a strict `max_chars=4000` limit.
- **Neighbor Expansion**: A function `_expand_neighbor_chunks` exists but is **never called**.

## 2. Identified Root Causes for "Not Found" Failures
When users complain that answers exist in the provided documents but the LLM responds with "Not found in the provided documents," the root causes are:

### A. Severe Context Clipping (Token Truncation)
In `Milvus.py`, `_format_context` defaults to `max_chars=4000` (~1000 tokens). A single chunk is ~1000 characters. With K=6 retrieval, plus potential syllabus augmentation, the pipeline retrieves 6000–8000+ characters. `_format_context` silently drops the latter half of the chunks. If the answer resides in the truncated chunks, the LLM literally never sees it.

### B. Broken Chunk Ordering
`_retrieve_docs` returns chunks sorted by rerank score. `_augment_docs_for_syllabus` appends extra chunks to the *end* of the list. `_format_context` concatenates them exactly in this scrambled order. This destroys document continuity. The LLM reads broken, fragmented text (e.g., Chunk 5, then Chunk 2, then Chunk 6). Furthermore, because of (A), the syllabus-augmented chunks placed at the end are *always* the ones getting truncated.

### C. Missing Neighbor Chunk Retrieval
`_expand_neighbor_chunks` is defined but never invoked in the main retrieval pipeline. If an answer straddles a chunk boundary, the LLM only gets half the context, which often leads to it refusing to answer or answering incorrectly.

### D. Redundant Context Merging
Chunks are created with `CHUNK_OVERLAP = 200`. When consecutive chunks are concatenated, the overlapping 200 characters are repeated twice. This wastes the already heavily-clipped context window and confuses the LLM with stuttering text.

## 3. Recommended Code Changes and Fixes

### Fix 1: Resolve Context Clipping
In `rag/llm_orchestration.py`, explicitly pass a much higher `max_chars` limit to `_format_context`, or modify the default in `Milvus.py`.
```python
# llm_orchestration.py
# Increase max_chars to accommodate at least 8-10 chunks (e.g., 32000 chars)
context = _format_context(docs, max_chars=32000)
```

### Fix 2: Enforce Sequential Chunk Ordering
In `rag/llm_orchestration.py`, sort the `docs` list by document source and chunk index *before* formatting the context. This restores natural reading order and ensures that adjacent chunks are placed consecutively.
```python
# llm_orchestration.py
docs = _augment_docs_for_syllabus(question, _retrieve_docs(question))
if not docs:
    return INSUFFICIENT_CONTEXT_MESSAGE

# Re-order by source and chunk index to restore continuity
docs.sort(key=lambda d: (
    (d.metadata or {}).get('source', ''),
    (d.metadata or {}).get('page_number', 0),
    (d.metadata or {}).get('chunk_index', 0)
))

context = _format_context(docs, max_chars=32000)
```

### Fix 3: Implement Neighbor Chunk Expansion
In `Milvus.py`, call `_expand_neighbor_chunks` at the end of `_retrieve_docs` to ensure bounded chunks are contextually whole.
```python
# Milvus.py inside _retrieve_docs, before returning:
try:
    cfg = _get_milvus_config()
    client = _connect_milvus_client(cfg)
    expanded = []
    seen = set()
    for doc in reranked_docs[:max(k, 4)]:
        neighbors = _expand_neighbor_chunks(doc, client, cfg["collection"])
        for n in neighbors:
            key = (n.metadata.get("source"), n.metadata.get("chunk_index"))
            if key not in seen:
                expanded.append(n)
                seen.add(key)
    return expanded
except Exception as e:
    logger.error(f"Neighbor expansion failed: {e}")
    return reranked_docs[:max(k, 4)]
```

### Fix 4: Context Merging for Overlaps
Update `_format_context` in `Milvus.py` to merge adjacent chunks by stripping out the known `CHUNK_OVERLAP`. If Chunk N and Chunk N+1 are from the same source, remove the trailing overlap from Chunk N before concatenating.
```python
# Pseudo-logic for Milvus.py context merging:
def merge_overlap(text1, text2, overlap_estimate=200):
    # Detect exact suffix-prefix match and merge smoothly
    for i in range(min(len(text1), len(text2), overlap_estimate + 100), 0, -1):
        if text1[-i:] == text2[:i]:
            return text1 + text2[i:]
    return text1 + "\n" + text2
```

### Fix 5: Unify Deduplication Keys
In `_augment_docs_for_syllabus`, the deduplication uses `document_path`, whereas `_rrf_fuse` uses `source`. Align these to both use `source` (or `document_path` consistently) to prevent duplicate chunks slipping through.
