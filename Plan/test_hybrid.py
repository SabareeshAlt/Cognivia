import os
import sys
import time
from collections import defaultdict

# Add the project root to sys.path so we can import Milvus
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import Milvus

def test_query(query: str):
    print(f"\n" + "="*80)
    print(f"Testing Query: '{query}'")
    print("="*80)
    
    start_time = time.perf_counter()
    
    # Try hybrid_search if exposed by the refactored Milvus.py, else default to _retrieve_docs pipeline
    func_to_call = getattr(Milvus, 'hybrid_search', getattr(Milvus, '_retrieve_docs', None))
    
    if not func_to_call:
        print("Error: Could not find hybrid_search or _retrieve_docs in Milvus.py.")
        return

    try:
        if func_to_call.__name__ == 'hybrid_search':
            try:
                docs = func_to_call(query, k=5)
            except TypeError:
                docs = func_to_call(query)
        else:
            docs = func_to_call(query)
    except Exception as e:
        print(f"Error during retrieval: {e}")
        return

    latency_ms = (time.perf_counter() - start_time) * 1000
    print(f"Retrieval latency: {latency_ms:.2f} ms (Verifies parallel execution overhead)")
    print(f"Total chunks retrieved: {len(docs)}")
    
    # Analyze chunk indices for neighbor fetching verification
    sources_chunks = defaultdict(list)
    for doc in docs:
        meta = doc.metadata or {}
        source = meta.get("source", "Unknown")
        chunk_idx = meta.get("chunk_index")
        if chunk_idx is not None:
            sources_chunks[source].append(chunk_idx)
            
    print("\n--- Neighbor Fetching Analysis ---")
    for source, indices in sources_chunks.items():
        sorted_indices = sorted(indices)
        print(f"Source: {source} -> Chunk Indices: {sorted_indices}")
        # Identify contiguous blocks
        blocks = []
        if sorted_indices:
            current_block = [sorted_indices[0]]
            for idx in sorted_indices[1:]:
                if idx == current_block[-1] + 1:
                    current_block.append(idx)
                else:
                    blocks.append(current_block)
                    current_block = [idx]
            blocks.append(current_block)
            
            contiguous = [b for b in blocks if len(b) > 1]
            if contiguous:
                print(f"  -> Found contiguous neighbor chunks: {contiguous}")
            else:
                print("  -> No contiguous neighbor chunks found.")
    
    print("\n--- Detailed Results ---")
    for i, doc in enumerate(docs):
        meta = doc.metadata or {}
        chunk_idx = meta.get("chunk_index", "N/A")
        page_num = meta.get("page_number", "N/A")
        source = meta.get("source", "N/A")
        
        # Check for RRF and separate scores (expected from true hybrid implementation)
        rrf_score = meta.get("rrf_score", "N/A")
        vector_score = meta.get("vector_score", "N/A")
        bm25_score = meta.get("bm25_score", "N/A")
        
        if rrf_score != "N/A":
            score_str = f"RRF: {rrf_score:.4f}"
            if vector_score != "N/A" or bm25_score != "N/A":
                score_str += f" (Vector: {vector_score}, BM25: {bm25_score})"
        else:
            # Fallback to standard score representation if RRF not explicitly set
            score = meta.get("score", "N/A")
            if isinstance(score, float):
                score_str = f"Score: {score:.4f}"
            else:
                score_str = f"Score: {score}"
            
        print(f"\nResult {i+1}:")
        print(f"  Source      : {source} (Page {page_num})")
        print(f"  Chunk Index : {chunk_idx}")
        print(f"  Metrics     : {score_str}")
        
        content_preview = doc.page_content.replace('\n', ' ')[:120]
        print(f"  Content     : {content_preview}...")

def main():
    print("Testing Hybrid Retrieval Pipeline...")
    
    queries = [
        "What are the objectives of Digital Logic Design?",
        "Explain the continuous assessment methodology.",
        "Give me the syllabus for Data Structures.",
        "What is the theory of computation?"
    ]
    
    for q in queries:
        test_query(q)

if __name__ == "__main__":
    main()
