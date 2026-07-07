#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced RAG Evaluation Harness for AcademeRAG
Provides:
- Precision@k, Recall@k, MRR, NDCG@5 for Retrieval
- Keyword Hit Rate & Citation Validation for Generation
- LLM-as-a-judge Metrics: Faithfulness, Answer Relevancy, Context Recall, Context Precision
- Category-wise reports, Failure analysis, and Retrieval Ablation Studies
"""

import argparse
import json
import statistics
import sys
import re
import requests
import os
import time
import math
from pathlib import Path
from typing import Any, List, Dict
from collections import defaultdict
from dotenv import load_dotenv

# Ensure we can import the backend modular RAG
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
load_dotenv(project_root / ".env")

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rag_project.settings')
django.setup()

# Import from the database package
try:
    from rag.llm_orchestration import get_optimized_response
    from database import _retrieve_docs
    # Import internal search legs for ablation study
    from database.retrieval import (
        _dense_search_pipeline,
        _search_bm25_fallback,
        _rrf_fuse,
        _cross_encoder_rerank,
        _compute_dynamic_top_k,
        _extract_target_sources,
        _preprocess_query
    )
except ImportError:
    from database import _retrieve_docs
    try:
        from rag.llm_orchestration import get_optimized_response
    except ImportError:
        get_optimized_response = None


class LLMEvaluator:
    def __init__(self, provider=None, model=None):
        self.provider = provider or os.environ.get("ACADEMERAG_EVAL_JUDGE_PROVIDER", "groq")
        self.model = model or os.environ.get("ACADEMERAG_EVAL_JUDGE_MODEL", "openai/gpt-oss-120b")
        self.ollama_endpoint = os.environ.get("OLLAMA_HEALTHCHECK_URL", "http://localhost:11434").replace("/health", "") or "http://localhost:11434"
        if not self.ollama_endpoint.endswith("/api/generate"):
            self.ollama_endpoint = self.ollama_endpoint.rstrip("/") + "/api/generate"
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()

    def _call_llm(self, prompt: str) -> str:
        if self.provider == "groq" and self.groq_api_key:
            try:
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 100
                }
                headers = {
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                }
                response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"Error calling Groq judge: {e}, falling back to local Ollama...")
        
        # Ollama fallback via chat endpoint
        fallback_model = self.model if self.provider == "ollama" else "gemma4:latest"
        url = self.ollama_endpoint
        if "/api/generate" in url:
            chat_url = url.replace("/api/generate", "/api/chat")
        else:
            chat_url = url.rstrip("/") + "/api/chat"
            
        payload = {
            "model": fallback_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.0}
        }
        try:
            response = requests.post(chat_url, json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"Error calling Ollama judge: {e}")
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

    def evaluate_context_precision(self, question: str, chunks: List[str]) -> float:
        if not chunks:
            return 0.0
            
        chunks_str = ""
        for idx, chunk in enumerate(chunks, 1):
            chunks_str += f"[Chunk {idx}]: {chunk}\n\n"
            
        prompt = f"""
        You are an evaluator. Given a question and a list of retrieved document chunks, determine for each chunk whether it is useful/relevant for answering the question.
        
        Question: {question}
        
        Retrieved Chunks:
        {chunks_str}
        
        For each chunk, output 1 if it contains information that is useful/relevant to answer the question, or 0 if it is irrelevant/not useful.
        Your output must be exactly a comma-separated list of 1s and 0s corresponding to the chunks (e.g. "1, 0, 1, 0, 0"). Do not output any markdown code block backticks, just the comma-separated list.
        """
        response = self._call_llm(prompt)
        revelances = [int(x) for x in re.findall(r'\b(0|1)\b', response)]
        
        if len(revelances) != len(chunks):
            parts = response.split(",")
            try:
                revelances = [1 if '1' in p else 0 for p in parts][:len(chunks)]
            except Exception:
                revelances = [0] * len(chunks)
                
        if len(revelances) < len(chunks):
            revelances += [0] * (len(chunks) - len(revelances))
            
        num_relevant = sum(revelances)
        if num_relevant == 0:
            return 0.0
            
        precision_sum = 0.0
        relevant_so_far = 0
        for idx, rel in enumerate(revelances, 1):
            if rel == 1:
                relevant_so_far += 1
                precision_sum += (relevant_so_far / idx)
                
        return precision_sum / num_relevant

    def explain_failure(self, question: str, context: str, answer: str, scores: Dict[str, float]) -> Dict[str, str]:
        prompt = f"""
        You are an expert failure analyst for Retrieval-Augmented Generation (RAG) systems.
        A RAG evaluation case has failed. Here is the data:
        
        Question: {question}
        Retrieved Context: {context[:2000]}
        Generated Answer: {answer}
        
        Evaluation Scores:
        - Faithfulness: {scores.get('faithfulness', 0.0)}
        - Answer Relevancy: {scores.get('answer_relevancy', 0.0)}
        - Context Recall: {scores.get('context_recall', 0.0)}
        - Context Precision: {scores.get('context_precision', 0.0)}
        
        Analyze the failure and provide:
        1. An explanation (1-2 sentences) describing why the system failed (e.g. context was missing details, model hallucinated external facts, answer was irrelevant, or citations were missing).
        2. A failure category (exactly one of: "Retrieval Failure", "Generation Hallucination", "Citation Violation", "Irrelevant Answer", "Keyword Miss", "Negative Rejection Failure", "Unknown").
        
        Output format:
        Explanation: <explanation text>
        Category: <category name>
        """
        response = self._call_llm(prompt)
        
        explanation = "Unable to generate explanation."
        category = "Unknown"
        
        exp_match = re.search(r'(?i)Explanation:\s*(.*)', response)
        cat_match = re.search(r'(?i)Category:\s*(.*)', response)
        
        if exp_match:
            explanation = exp_match.group(1).strip()
        if cat_match:
            category = cat_match.group(1).strip()
            valid_categories = ["Retrieval Failure", "Generation Hallucination", "Citation Violation", "Irrelevant Answer", "Keyword Miss", "Negative Rejection Failure", "Unknown"]
            found = False
            for vc in valid_categories:
                if vc.lower() in category.lower():
                    category = vc
                    found = True
                    break
            if not found:
                category = "Unknown"
                
        return {"explanation": explanation, "category": category}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def calculate_mrr(retrieved_sources, expected_sources):
    for rank, source in enumerate(retrieved_sources, 1):
        if any(exp in source for exp in expected_sources):
            return 1.0 / rank
    return 0.0

def calculate_ndcg(retrieved_sources, expected_sources, k=5):
    if not expected_sources:
        return 1.0 if not retrieved_sources else 0.0
        
    dcg = 0.0
    for idx, src in enumerate(retrieved_sources[:k], 1):
        if any(exp in src for exp in expected_sources):
            dcg += 1.0 / math.log2(idx + 1)
            
    idcg = 0.0
    for idx in range(1, min(k, len(expected_sources)) + 1):
        idcg += 1.0 / math.log2(idx + 1)
        
    return dcg / idcg if idcg > 0.0 else 0.0

def evaluate_retrieval(question: str, expected_sources: list, k: int = 5):
    docs = _retrieve_docs(question)
    retrieved_sources = [doc.metadata.get('source', '') for doc in docs[:k]]
    retrieved_contexts = [doc.page_content for doc in docs[:k]]
    
    hits = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
    precision_at_k = hits / len(retrieved_sources) if retrieved_sources else 0.0
    recall_at_k = hits / len(expected_sources) if expected_sources else (1.0 if not expected_sources else 0.0)
    mrr = calculate_mrr(retrieved_sources, expected_sources)
    ndcg = calculate_ndcg(retrieved_sources, expected_sources, k)
    
    context_str = "\n\n".join(retrieved_contexts)
    return precision_at_k, recall_at_k, mrr, ndcg, context_str, retrieved_contexts

def evaluate_generation(question: str, reference_keywords: list, expected_sources: list):
    answer = get_optimized_response(question)
    answer_l = answer.lower()
    
    keywords = [k.lower() for k in reference_keywords]
    keyword_hits = sum(1 for k in keywords if k in answer_l)
    keyword_hit_rate = keyword_hits / len(keywords) if keywords else 1.0
    
    has_citation = bool(re.search(r'\[Source:\s*[^,\\]]+(?:,\s*Page:?\s*\d+)?\]', answer, re.IGNORECASE))
    return keyword_hit_rate, has_citation, answer


def run_retrieval_ablation(dataset: List[Dict], k: int = 5) -> Dict[str, Dict]:
    pos_cases = [c for c in dataset if c.get("expected_sources")]
    if not pos_cases:
        pos_cases = dataset
        
    ablation_results = {}
    configs = ["Dense Only", "BM25 Only", "Hybrid", "Hybrid + Cross Encoder"]
    
    for config in configs:
        print(f"Running ablation benchmark for: {config}...")
        precisions = []
        recalls = []
        mrrs = []
        ndcgs = []
        retrieval_latencies = []
        reranker_latencies = []
        total_latencies = []
        
        for case in pos_cases:
            q = case["question"]
            expected_sources = case.get("expected_sources", [])
            
            q_processed = _preprocess_query(q)
            search_k = max(40, k * 4)
            
            start_total = time.perf_counter()
            
            start_ret = time.perf_counter()
            dense_docs = []
            bm25_docs = []
            
            if config in ["Dense Only", "Hybrid", "Hybrid + Cross Encoder"]:
                try:
                    dense_docs = _dense_search_pipeline(q_processed, search_k, None)
                except Exception:
                    pass
            if config in ["BM25 Only", "Hybrid", "Hybrid + Cross Encoder"]:
                try:
                    bm25_docs = _search_bm25_fallback(q_processed, search_k, None)
                except Exception:
                    pass
                    
            if config == "Dense Only":
                retrieved_docs = dense_docs
            elif config == "BM25 Only":
                retrieved_docs = bm25_docs
            else:
                retrieved_docs = _rrf_fuse(dense_docs, bm25_docs, search_k)
                
            ret_lat = (time.perf_counter() - start_ret) * 1000
            
            start_rerank = time.perf_counter()
            if config == "Hybrid + Cross Encoder":
                try:
                    final_docs = _cross_encoder_rerank(q_processed, retrieved_docs, k)
                except Exception:
                    final_docs = retrieved_docs[:k]
            else:
                final_docs = retrieved_docs[:k]
            rerank_lat = (time.perf_counter() - start_rerank) * 1000
            
            tot_lat = (time.perf_counter() - start_total) * 1000
            
            retrieved_sources = [doc.metadata.get('source', '') for doc in final_docs]
            
            hits = sum(1 for src in retrieved_sources if any(exp in src for exp in expected_sources))
            p_at_k = hits / len(retrieved_sources) if retrieved_sources else 0.0
            r_at_k = hits / len(expected_sources) if expected_sources else 0.0
            mrr = calculate_mrr(retrieved_sources, expected_sources)
            ndcg = calculate_ndcg(retrieved_sources, expected_sources, k)
            
            precisions.append(p_at_k)
            recalls.append(r_at_k)
            mrrs.append(mrr)
            ndcgs.append(ndcg)
            retrieval_latencies.append(ret_lat)
            reranker_latencies.append(rerank_lat if config == "Hybrid + Cross Encoder" else 0.0)
            total_latencies.append(tot_lat)
            
        ablation_results[config] = {
            "precision": statistics.mean(precisions),
            "recall": statistics.mean(recalls),
            "mrr": statistics.mean(mrrs),
            "ndcg": statistics.mean(ndcgs),
            "avg_retrieval_latency": statistics.mean(retrieval_latencies),
            "avg_reranker_latency": statistics.mean(reranker_latencies),
            "avg_total_latency": statistics.mean(total_latencies)
        }
        
    return ablation_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="eval/golden_set_academic.json")
    parser.add_argument("--k", type=int, default=5, help="Top-K for retrieval metrics")
    parser.add_argument("--judge-provider", type=str, default=None, help="Judge provider: groq or ollama")
    parser.add_argument("--judge-model", type=str, default=None, help="Judge model to use as evaluator")
    parser.add_argument("--mode", type=str, default="live", help="Evaluation mode: live or mock")
    parser.add_argument("--output", type=str, default="eval/latest_report.json", help="Output JSON path")
    parser.add_argument("--sample", type=int, default=None, help="Number of queries to sample for quick evaluation")
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    
    if args.sample:
        by_cat = defaultdict(list)
        for c in dataset:
            by_cat[c.get("type", "Unknown")].append(c)
            
        sampled = []
        cat_keys = list(by_cat.keys())
        idx = 0
        while len(sampled) < args.sample and any(by_cat.values()):
            curr_cat = cat_keys[idx % len(cat_keys)]
            if by_cat[curr_cat]:
                sampled.append(by_cat[curr_cat].pop(0))
            idx += 1
        dataset = sampled
        print(f"Sampled {len(dataset)} balanced queries for evaluation.")
    
    if args.mode == "mock":
        print("Running in MOCK mode. Bypassing live LLM evaluation.")
        results = [{"id": case["id"], "passed": True} for case in dataset]
        summary = {"total_cases": len(results), "overall_pass_rate": 1.0}
        
        output_path = Path(args.output)
        output_path.parent.mkdir(exist_ok=True, parents=True)
        output_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2))
        return

    evaluator = LLMEvaluator(provider=args.judge_provider, model=args.judge_model)
    
    results = []
    category_results = defaultdict(list)
    failures = []
    
    print(f"Evaluating {len(dataset)} cases using {evaluator.provider}/{evaluator.model} as judge...")
    
    overall_start_time = time.perf_counter()
    
    for i, case in enumerate(dataset):
        q = case["question"]
        expected_sources = case.get("expected_sources", [])
        keywords = case.get("reference_keywords", [])
        raw_category = case.get("type", "Unknown")
        category = "Negative Queries" if raw_category in ["Negative Retrieval", "Negative Queries"] else raw_category
        
        print(f"[{i+1}/{len(dataset)}] Evaluating: {q[:50]}...")
        
        start_query = time.perf_counter()
        
        # 1. Retrieval Eval
        start_ret = time.perf_counter()
        p_at_k, r_at_k, mrr, ndcg, context_str, retrieved_contexts = evaluate_retrieval(q, expected_sources, args.k)
        ret_latency = (time.perf_counter() - start_ret) * 1000
        
        # 2. Generation Eval
        start_gen = time.perf_counter()
        hit_rate, has_citation, answer = evaluate_generation(q, keywords, expected_sources)
        gen_latency = (time.perf_counter() - start_gen) * 1000
        
        # 3. LLM-as-a-judge Eval
        faithfulness = evaluator.evaluate_faithfulness(q, context_str, answer)
        answer_relevancy = evaluator.evaluate_answer_relevancy(q, answer)
        context_recall = evaluator.evaluate_context_recall(q, context_str)
        context_precision = evaluator.evaluate_context_precision(q, retrieved_contexts)
        
        total_latency = (time.perf_counter() - start_query) * 1000
        
        passed = hit_rate >= 0.7 and (has_citation or "not found" in answer.lower()) and (mrr > 0 or not expected_sources) and faithfulness > 0 and answer_relevancy > 0
        
        res = {
            "id": case["id"],
            "question": q,
            "category": category,
            "precision_at_k": p_at_k,
            "recall_at_k": r_at_k,
            "mrr": mrr,
            "ndcg": ndcg,
            "keyword_hit_rate": hit_rate,
            "has_citation": has_citation,
            "faithfulness": faithfulness,
            "answer_relevancy": answer_relevancy,
            "context_recall": context_recall,
            "context_precision": context_precision,
            "passed": passed,
            "latency": {
                "retrieval": ret_latency,
                "generation": gen_latency,
                "total": total_latency
            }
        }
        
        results.append(res)
        category_results[category].append(res)
        
        if not passed:
            print(f"   -> FAILURE DETECTED. Running failure analysis...")
            scores = {
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "context_recall": context_recall,
                "context_precision": context_precision
            }
            analysis = evaluator.explain_failure(q, context_str, answer, scores)
            
            failures.append({
                "id": case["id"],
                "question": q,
                "expected_answer": f"Expected sources: {expected_sources}, Keywords: {keywords}",
                "retrieved_context": context_str,
                "generated_answer": answer,
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "context_recall": context_recall,
                "context_precision": context_precision,
                "judge_explanation": analysis["explanation"],
                "failure_category": analysis["category"]
            })
            
    # Calculate global averages
    avg_p = statistics.mean([r["precision_at_k"] for r in results])
    avg_r = statistics.mean([r["recall_at_k"] for r in results])
    avg_mrr = statistics.mean([r["mrr"] for r in results])
    avg_ndcg = statistics.mean([r["ndcg"] for r in results])
    avg_hit_rate = statistics.mean([r["keyword_hit_rate"] for r in results])
    
    avg_faithfulness = statistics.mean([r["faithfulness"] for r in results])
    avg_answer_relevancy = statistics.mean([r["answer_relevancy"] for r in results])
    avg_context_recall = statistics.mean([r["context_recall"] for r in results])
    avg_context_precision = statistics.mean([r["context_precision"] for r in results])
    
    citation_rate = sum(1 for r in results if r["has_citation"]) / len(results)
    pass_rate = sum(1 for r in results if r["passed"]) / len(results)
    
    avg_ret_lat = statistics.mean([r["latency"]["retrieval"] for r in results])
    avg_gen_lat = statistics.mean([r["latency"]["generation"] for r in results])
    avg_tot_lat = statistics.mean([r["latency"]["total"] for r in results])

    summary = {
        "total_cases": len(results),
        "overall_pass_rate": pass_rate,
        "retrieval_metrics": {
            "mean_precision@k": avg_p,
            "mean_recall@k": avg_r,
            "mrr": avg_mrr,
            "mean_ndcg@5": avg_ndcg,
            "mean_context_recall": avg_context_recall,
            "mean_context_precision": avg_context_precision
        },
        "generation_metrics": {
            "avg_keyword_hit_rate": avg_hit_rate,
            "citation_rate": citation_rate,
            "mean_faithfulness": avg_faithfulness,
            "mean_answer_relevancy": avg_answer_relevancy
        },
        "latency_metrics": {
            "avg_retrieval_latency_ms": avg_ret_lat,
            "avg_generation_latency_ms": avg_gen_lat,
            "avg_total_latency_ms": avg_tot_lat
        }
    }
    
    # ─── Category Reports ──────────────────────────────────────────────────────
    print("\nGenerating Category-wise Evaluation Report...")
    category_summary = {}
    for cat, cat_res in category_results.items():
        cat_pass_rate = sum(1 for r in cat_res if r["passed"]) / len(cat_res)
        category_summary[cat] = {
            "total_cases": len(cat_res),
            "pass_rate": cat_pass_rate,
            "faithfulness": statistics.mean([r["faithfulness"] for r in cat_res]),
            "answer_relevancy": statistics.mean([r["answer_relevancy"] for r in cat_res]),
            "context_recall": statistics.mean([r["context_recall"] for r in cat_res]),
            "context_precision": statistics.mean([r["context_precision"] for r in cat_res]),
            "precision_at_k": statistics.mean([r["precision_at_k"] for r in cat_res]),
            "recall_at_k": statistics.mean([r["recall_at_k"] for r in cat_res]),
            "mrr": statistics.mean([r["mrr"] for r in cat_res]),
            "ndcg": statistics.mean([r["ndcg"] for r in cat_res])
        }
        
    doc_dir = project_root / "documentation"
    doc_dir.mkdir(exist_ok=True)
    
    # Write Category Report MD
    cat_report_path = doc_dir / "evaluation_category_report.md"
    cat_md = ["# AcademeRAG Category-wise Evaluation Report\n"]
    cat_md.append("| Category | Total Cases | Pass Rate | Faithfulness | Answer Relevancy | Context Recall | Context Precision |")
    cat_md.append("|---|---|---|---|---|---|---|")
    for cat, s in category_summary.items():
        cat_md.append(f"| {cat} | {s['total_cases']} | {s['pass_rate']:.2%} | {s['faithfulness']:.4f} | {s['answer_relevancy']:.4f} | {s['context_recall']:.4f} | {s['context_precision']:.4f} |")
    cat_report_path.write_text("\n".join(cat_md), encoding="utf-8")
    
    # ─── Failure Analysis Reports ──────────────────────────────────────────────
    print("Generating Failure Analysis Report...")
    fail_report_path = doc_dir / "evaluation_failures.md"
    fail_md = ["# AcademeRAG Evaluation Failure Reports\n"]
    if not failures:
        fail_md.append("All evaluation cases passed successfully! No failures recorded.")
    else:
        for idx, f in enumerate(failures, 1):
            fail_md.append(f"## Failure case {idx} (ID: {f['id']})")
            fail_md.append(f"- **Category**: {f['failure_category']}")
            fail_md.append(f"- **Question**: {f['question']}")
            fail_md.append(f"- **Expected**: {f['expected_answer']}")
            fail_md.append(f"- **Retrieved Context**: \n```\n{f['retrieved_context'][:500]}...\n```")
            fail_md.append(f"- **Generated Answer**: \n```\n{f['generated_answer']}\n```")
            fail_md.append(f"- **Metrics**: Faithfulness: {f['faithfulness']:.1f}, Relevancy: {f['answer_relevancy']:.1f}, Recall: {f['context_recall']:.1f}, Precision: {f['context_precision']:.2f}")
            fail_md.append(f"- **Judge Explanation**: {f['judge_explanation']}\n")
    fail_report_path.write_text("\n".join(fail_md), encoding="utf-8")
    
    # ─── Retrieval Ablation Study ──────────────────────────────────────────────
    print("Running Retrieval Ablation Study...")
    ablation_results = run_retrieval_ablation(dataset, args.k)
    
    ablation_report_path = doc_dir / "retrieval_ablation.md"
    abl_md = ["# AcademeRAG Retrieval Ablation Study\n"]
    abl_md.append("| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Avg Retrieval Latency (ms) | Avg Reranker Latency (ms) | Avg Total Latency (ms) |")
    abl_md.append("|---|---|---|---|---|---|---|---|")
    for config, metrics in ablation_results.items():
        abl_md.append(f"| {config} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['mrr']:.4f} | {metrics['ndcg']:.4f} | {metrics['avg_retrieval_latency']:.1f} | {metrics['avg_reranker_latency']:.1f} | {metrics['avg_total_latency']:.1f} |")
    ablation_report_path.write_text("\n".join(abl_md), encoding="utf-8")
    
    # ─── Evaluation Summary ────────────────────────────────────────────────────
    print("Generating Final Evaluation Summary Report...")
    sum_report_path = doc_dir / "evaluation_summary.md"
    
    # Highlight logic
    best_cat = max(category_summary.keys(), key=lambda k: category_summary[k]["pass_rate"])
    worst_cat = min(category_summary.keys(), key=lambda k: category_summary[k]["pass_rate"])
    
    failure_counts = defaultdict(int)
    for f in failures:
        failure_counts[f["failure_category"]] += 1
    largest_failure_mode = max(failure_counts.keys(), key=lambda k: failure_counts[k]) if failures else "None"
    
    mean_recall = summary["retrieval_metrics"]["mean_recall@k"]
    mean_precision = summary["retrieval_metrics"]["mean_precision@k"]
    mean_faithfulness = summary["generation_metrics"]["mean_faithfulness"]
    mean_relevancy = summary["generation_metrics"]["mean_answer_relevancy"]
    
    largest_retrieval_weakness = "Recall" if mean_recall < mean_precision else "Precision"
    largest_generation_weakness = "Faithfulness" if mean_faithfulness < mean_relevancy else "Answer Relevancy"
    
    sum_md = [
        "# AcademeRAG Evaluation Summary Report\n",
        "## Overall Metrics",
        f"- **Total Cases**: {summary['total_cases']}",
        f"- **Overall Pass Rate**: {summary['overall_pass_rate']:.2%}",
        f"- **Average Retrieval Latency**: {summary['latency_metrics']['avg_retrieval_latency_ms']:.1f} ms",
        f"- **Average Generation Latency**: {summary['latency_metrics']['avg_generation_latency_ms']:.1f} ms",
        f"- **Average Total Latency**: {summary['latency_metrics']['avg_total_latency_ms']:.1f} ms\n",
        "## Per-Category Performance",
        "| Category | Pass Rate | MRR | NDCG@5 | Faithfulness | Relevancy | Context Precision |",
        "|---|---|---|---|---|---|---|",
    ]
    for cat, s in category_summary.items():
        sum_md.append(f"| {cat} | {s['pass_rate']:.2%} | {s['mrr']:.4f} | {s['ndcg']:.4f} | {s['faithfulness']:.4f} | {s['answer_relevancy']:.4f} | {s['context_precision']:.4f} |")
        
    sum_md.extend([
        "\n## Retrieval Ablation Benchmarks",
        "| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Total Latency (ms) |",
        "|---|---|---|---|---|---|",
    ])
    for config, metrics in ablation_results.items():
        sum_md.append(f"| {config} | {metrics['precision']:.4f} | {metrics['recall']:.4f} | {metrics['mrr']:.4f} | {metrics['ndcg']:.4f} | {metrics['avg_total_latency']:.1f} |")
        
    sum_md.extend([
        "\n## Highlights",
        f"- **Best Performing Category**: {best_cat} ({category_summary[best_cat]['pass_rate']:.2%} pass rate)",
        f"- **Worst Performing Category**: {worst_cat} ({category_summary[worst_cat]['pass_rate']:.2%} pass rate)",
        f"- **Largest Failure Mode**: {largest_failure_mode} ({failure_counts[largest_failure_mode]} occurrences)" if failures else "- **Largest Failure Mode**: None",
        f"- **Largest Retrieval Weakness**: {largest_retrieval_weakness} (Mean Precision: {mean_precision:.4f}, Mean Recall: {mean_recall:.4f})",
        f"- **Largest Generation Weakness**: {largest_generation_weakness} (Mean Faithfulness: {mean_faithfulness:.4f}, Mean Relevancy: {mean_relevancy:.4f})",
        "\n## Failure Summary",
        f"- **Total Failures**: {len(failures)}"
    ])
    
    for cat, count in failure_counts.items():
        sum_md.append(f"  - {cat}: {count} ({count/len(failures):.1%})")
        
    sum_report_path.write_text("\n".join(sum_md), encoding="utf-8")
    
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True, parents=True)
    output_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")
    print(f"All reports successfully written to {doc_dir}/")

if __name__ == "__main__":
    main()
