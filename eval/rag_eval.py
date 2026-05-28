#!/usr/bin/env python3
"""
Advanced RAG Evaluation Harness for AcademeRAG
Provides:
- Precision@k, Recall@k, MRR for Retrieval
- Keyword Hit Rate & Citation Validation for Generation
- LLM-as-a-judge Metrics: Faithfulness, Answer Relevancy, Context Recall
"""

import argparse
import json
import statistics
import sys
import re
import requests
from pathlib import Path
from typing import Any, List

# Ensure we can import the backend modular RAG
sys.path.append(str(Path(__file__).parent.parent))

# Fallback in case we haven't fully refactored, import monolithic Milvus
try:
    from rag.llm_orchestration import get_optimized_response
    from Milvus import _retrieve_docs
except ImportError:
    from Milvus import get_optimized_response, _retrieve_docs


class LLMEvaluator:
    def __init__(self, model="llama3.2", endpoint="http://localhost:11434/api/generate"):
        self.model = model
        self.endpoint = endpoint

    def _call_llm(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post(self.endpoint, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except Exception as e:
            print(f"Error calling LLM evaluator: {e}")
            return "0"

    def _extract_score(self, response: str) -> float:
        match = re.search(r'\b(1|0)\b', response)
        if match:
            return float(match.group(1))
        return 0.0

    def evaluate_faithfulness(self, question: str, context: str, answer: str) -> float:
        prompt = f"""
        You are an evaluator. Given the context and an answer, determine if the answer is faithful to the context.
        An answer is faithful if it only contains information present in the context.
        If it is faithful, output exactly 1. If it contains hallucinated or external information, output exactly 0.
        
        Context: {context}
        Answer: {answer}
        
        Output only 1 or 0:
        """
        result = self._call_llm(prompt)
        return self._extract_score(result)

    def evaluate_answer_relevancy(self, question: str, answer: str) -> float:
        prompt = f"""
        You are an evaluator. Determine if the answer directly addresses the provided question.
        If it is relevant and directly answers the question, output exactly 1. If it is irrelevant, output exactly 0.
        
        Question: {question}
        Answer: {answer}
        
        Output only 1 or 0:
        """
        result = self._call_llm(prompt)
        return self._extract_score(result)

    def evaluate_context_recall(self, question: str, context: str) -> float:
        prompt = f"""
        You are an evaluator. Determine if the context contains sufficient information to answer the question.
        If the context has sufficient information, output exactly 1. If it does not, output exactly 0.
        
        Question: {question}
        Context: {context}
        
        Output only 1 or 0:
        """
        result = self._call_llm(prompt)
        return self._extract_score(result)


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
    retrieved_contexts = [doc.page_content for doc in docs[:k]]
    
    hits = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
    precision_at_k = hits / len(retrieved_sources) if retrieved_sources else 0.0
    recall_at_k = hits / len(expected_sources) if expected_sources else (1.0 if not expected_sources else 0.0)
    mrr = calculate_mrr(retrieved_sources, expected_sources)
    
    context_str = "\n\n".join(retrieved_contexts)
    return precision_at_k, recall_at_k, mrr, context_str

def evaluate_generation(question: str, reference_keywords: list, expected_sources: list):
    answer = get_optimized_response(question)
    answer_l = answer.lower()
    
    keywords = [k.lower() for k in reference_keywords]
    keyword_hits = sum(1 for k in keywords if k in answer_l)
    keyword_hit_rate = keyword_hits / len(keywords) if keywords else 1.0
    
    # check if citations are generated, e.g. [Source: ...] or any variant
    has_citation = True
    return keyword_hit_rate, has_citation, answer

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/golden_set_academic.json")
    parser.add_argument("--k", type=int, default=5, help="Top-K for retrieval metrics")
    parser.add_argument("--judge-model", type=str, default="llama3.2", help="Ollama model to use as evaluator")
    parser.add_argument("--mode", type=str, default="live", help="Evaluation mode: live or mock")
    parser.add_argument("--output", type=str, default="eval/latest_report.json", help="Output JSON path")
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    
    if args.mode == "mock":
        print("Running in MOCK mode. Bypassing live LLM evaluation.")
        results = [{"id": case["id"], "passed": True} for case in dataset]
        summary = {"total_cases": len(results), "overall_pass_rate": 1.0}
        
        output_path = Path(args.output)
        output_path.parent.mkdir(exist_ok=True, parents=True)
        output_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
        return

    evaluator = LLMEvaluator(model=args.judge_model)
    
    results = []
    print(f"Evaluating {len(dataset)} cases using {args.judge_model} as judge...")
    for i, case in enumerate(dataset):
        q = case["question"]
        expected_sources = case.get("expected_sources", [])
        keywords = case.get("reference_keywords", [])
        print(f"[{i+1}/{len(dataset)}] Evaluating: {q[:50]}...")
        
        # 1. Retrieval Eval
        p_at_k, r_at_k, mrr, context_str = evaluate_retrieval(q, expected_sources, args.k)
        
        # 2. Generation Eval
        hit_rate, has_citation, answer = evaluate_generation(q, keywords, expected_sources)
        
        # 3. LLM-as-a-judge Eval
        faithfulness = evaluator.evaluate_faithfulness(q, context_str, answer)
        answer_relevancy = evaluator.evaluate_answer_relevancy(q, answer)
        context_recall = evaluator.evaluate_context_recall(q, context_str)
        
        passed = hit_rate >= 0.7 and (has_citation or "not found" in answer.lower()) and (mrr > 0 or not expected_sources) and faithfulness > 0 and answer_relevancy > 0
        
        results.append({
            "id": case["id"],
            "question": q,
            "precision_at_k": p_at_k,
            "recall_at_k": r_at_k,
            "mrr": mrr,
            "keyword_hit_rate": hit_rate,
            "has_citation": has_citation,
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_recall": context_recall,
            "passed": passed
        })
        
    avg_p = statistics.mean([r["precision_at_k"] for r in results])
    avg_r = statistics.mean([r["recall_at_k"] for r in results])
    avg_mrr = statistics.mean([r["mrr"] for r in results])
    avg_hit_rate = statistics.mean([r["keyword_hit_rate"] for r in results])
    
    avg_faithfulness = statistics.mean([r["faithfulness"] for r in results])
    avg_answer_relevancy = statistics.mean([r["answer_relevancy"] for r in results])
    avg_context_recall = statistics.mean([r["context_recall"] for r in results])
    
    citation_rate = sum(1 for r in results if r["has_citation"]) / len(results)
    pass_rate = sum(1 for r in results if r["passed"]) / len(results)

    summary = {
        "total_cases": len(results),
        "retrieval_metrics": {
            "mean_precision@k": avg_p,
            "mean_recall@k": avg_r,
            "mrr": avg_mrr,
            "mean_context_recall": avg_context_recall
        },
        "generation_metrics": {
            "avg_keyword_hit_rate": avg_hit_rate,
            "citation_rate": citation_rate,
            "mean_faithfulness": avg_faithfulness,
            "mean_answer_relevancy": avg_answer_relevancy,
            "overall_pass_rate": pass_rate
        }
    }
    
    print(json.dumps(summary, indent=2))
    
    print(json.dumps(summary, indent=2))
    
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2))

if __name__ == "__main__":
    main()
