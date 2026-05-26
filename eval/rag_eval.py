#!/usr/bin/env python3
"""
Advanced RAG Evaluation Harness for AcademeRAG
Provides:
- Precision@k, Recall@k, MRR for Retrieval
- Keyword Hit Rate & Citation Validation for Generation
"""

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

# Ensure we can import the backend modular RAG
sys.path.append(str(Path(__file__).parent.parent))

# Fallback in case we haven't fully refactored, import monolithic Milvus
try:
    from rag.retrieval import get_retriever
    from rag.llm import get_optimized_response
except ImportError:
    from Milvus import get_retriever, get_optimized_response, _retrieve_docs

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def calculate_mrr(retrieved_sources, expected_sources):
    for rank, source in enumerate(retrieved_sources, 1):
        if any(exp in source for exp in expected_sources):
            return 1.0 / rank
    return 0.0

def evaluate_retrieval(question: str, expected_sources: list, k: int = 5):
    docs = _retrieve_docs(question)
    retrieved_sources = [doc.metadata.get('source', '') for doc in docs[:k]]
    
    hits = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
    precision_at_k = hits / len(retrieved_sources) if retrieved_sources else 0.0
    recall_at_k = hits / len(expected_sources) if expected_sources else 0.0
    mrr = calculate_mrr(retrieved_sources, expected_sources)
    
    return precision_at_k, recall_at_k, mrr

def evaluate_generation(question: str, reference_keywords: list):
    answer = get_optimized_response(question)
    answer_l = answer.lower()
    
    keywords = [k.lower() for k in reference_keywords]
    keyword_hits = sum(1 for k in keywords if k in answer_l)
    keyword_hit_rate = keyword_hits / len(keywords) if keywords else 1.0
    
    has_citation = "[Source:" in answer
    return keyword_hit_rate, has_citation, answer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/golden_set.json")
    parser.add_argument("--k", type=int, default=5, help="Top-K for retrieval metrics")
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    
    results = []
    for case in dataset:
        q = case["question"]
        expected_sources = case.get("expected_sources", [])
        keywords = case.get("reference_keywords", [])
        
        # 1. Retrieval Eval
        p_at_k, r_at_k, mrr = evaluate_retrieval(q, expected_sources, args.k)
        
        # 2. Generation Eval
        hit_rate, has_citation, answer = evaluate_generation(q, keywords)
        
        passed = hit_rate >= 0.7 and has_citation and mrr > 0
        
        results.append({
            "id": case["id"],
            "question": q,
            "precision_at_k": p_at_k,
            "recall_at_k": r_at_k,
            "mrr": mrr,
            "keyword_hit_rate": hit_rate,
            "has_citation": has_citation,
            "passed": passed
        })
        
    avg_p = statistics.mean([r["precision_at_k"] for r in results])
    avg_r = statistics.mean([r["recall_at_k"] for r in results])
    avg_mrr = statistics.mean([r["mrr"] for r in results])
    avg_hit_rate = statistics.mean([r["keyword_hit_rate"] for r in results])
    citation_rate = sum(1 for r in results if r["has_citation"]) / len(results)
    pass_rate = sum(1 for r in results if r["passed"]) / len(results)

    summary = {
        "total_cases": len(results),
        "retrieval_metrics": {
            "mean_precision@k": avg_p,
            "mean_recall@k": avg_r,
            "mrr": avg_mrr
        },
        "generation_metrics": {
            "avg_keyword_hit_rate": avg_hit_rate,
            "citation_rate": citation_rate,
            "overall_pass_rate": pass_rate
        }
    }
    
    print(json.dumps(summary, indent=2))
    
    output_path = Path("eval/latest_report.json")
    output_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

if __name__ == "__main__":
    main()
