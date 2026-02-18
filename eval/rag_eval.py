#!/usr/bin/env python3
"""Lightweight RAG regression harness.

Modes:
- mock: synthetic deterministic answers for CI smoke gates.
- live: call running backend /api/ask/ endpoint with JWT auth.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import requests


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def mock_answer(question: str) -> str:
    q = question.lower()
    if "retrieval-augmented generation" in q:
        return "RAG combines retrieval of relevant documents with generation grounded in those documents [doc-1]."
    if "hybrid retrieval" in q:
        return "Hybrid retrieval combines BM25 keyword search with vector similarity and reranking for precision [doc-2]."
    if "reduce hallucinations" in q:
        return "Reduce hallucinations through grounding, citation enforcement, and continuous evaluation gates [doc-3]."
    return "No answer available [doc-x]."


def live_answer(question: str, base_url: str, access_token: str) -> str:
    response = requests.post(
        f"{base_url.rstrip('/')}/api/ask/",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
        json={"question": question},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("answer", ""))


def score_case(case: dict, answer: str) -> dict:
    answer_l = answer.lower()
    keywords = [k.lower() for k in case.get("reference_keywords", [])]
    keyword_hits = sum(1 for k in keywords if k in answer_l)
    keyword_hit_rate = keyword_hits / len(keywords) if keywords else 1.0

    citation_markers = case.get("required_citation_markers", [])
    has_citation = any(marker in answer for marker in citation_markers) if citation_markers else True

    passed = keyword_hit_rate >= 0.6 and has_citation

    return {
        "id": case.get("id"),
        "question": case.get("question"),
        "answer": answer,
        "keyword_hit_rate": keyword_hit_rate,
        "has_citation": has_citation,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--dataset", default="eval/golden_set.json")
    parser.add_argument("--thresholds", default="eval/thresholds.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--access-token", default="")
    parser.add_argument("--output", default="eval/latest_report.json")
    args = parser.parse_args()

    dataset = load_json(Path(args.dataset))
    thresholds = load_json(Path(args.thresholds))

    results = []
    for case in dataset:
        if args.mode == "mock":
            answer = mock_answer(case["question"])
        else:
            if not args.access_token:
                print("--access-token is required in live mode", file=sys.stderr)
                return 2
            answer = live_answer(case["question"], args.base_url, args.access_token)

        results.append(score_case(case, answer))

    keyword_rates = [r["keyword_hit_rate"] for r in results]
    citation_rate = sum(1 for r in results if r["has_citation"]) / len(results)
    pass_rate = sum(1 for r in results if r["passed"]) / len(results)

    summary = {
        "mode": args.mode,
        "cases": len(results),
        "avg_keyword_hit_rate": statistics.mean(keyword_rates) if keyword_rates else 0.0,
        "citation_rate": citation_rate,
        "pass_rate": pass_rate,
        "thresholds": thresholds,
        "meets_thresholds": (
            statistics.mean(keyword_rates) >= thresholds["min_keyword_hit_rate"]
            and citation_rate >= thresholds["min_citation_rate"]
            and pass_rate >= thresholds["min_pass_rate"]
        ),
    }

    output_payload = {"summary": summary, "results": results}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if summary["meets_thresholds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
