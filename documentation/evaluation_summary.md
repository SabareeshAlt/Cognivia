# AcademeRAG Evaluation Summary Report

## Overall Metrics
- **Total Cases**: 15
- **Overall Pass Rate**: 13.33%
- **Average Retrieval Latency**: 10556.4 ms
- **Average Generation Latency**: 19500.0 ms
- **Average Total Latency**: 55357.2 ms

## Per-Category Performance
| Category | Pass Rate | MRR | NDCG@5 | Faithfulness | Relevancy | Context Precision |
|---|---|---|---|---|---|---|
| Factual QA | 0.00% | 1.0000 | 0.8357 | 0.0000 | 0.5000 | 0.5000 |
| Syllabus QA | 0.00% | 1.0000 | 0.4693 | 0.0000 | 1.0000 | 0.5000 |
| Keyword Lookup | 0.00% | 1.0000 | 0.5703 | 0.0000 | 0.0000 | 0.0000 |
| Summarization | 0.00% | 1.0000 | 0.8357 | 0.0000 | 1.0000 | 0.5271 |
| Negative Queries | 100.00% | 0.0000 | 0.0000 | 1.0000 | 1.0000 | 0.1000 |
| Multi-page Reasoning | 0.00% | 1.0000 | 0.8357 | 0.0000 | 0.5000 | 0.5000 |
| Table Extraction | 0.00% | 1.0000 | 0.7346 | 0.0000 | 1.0000 | 0.3750 |
| Semantic Retrieval | 0.00% | 1.0000 | 0.4693 | 0.0000 | 1.0000 | 0.0000 |

## Retrieval Ablation Benchmarks
| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Total Latency (ms) |
|---|---|---|---|---|---|
| Dense Only | 0.2462 | 0.6154 | 0.9487 | 0.6530 | 4019.9 |
| BM25 Only | 0.4000 | 0.6154 | 0.9231 | 0.6668 | 720.6 |
| Hybrid | 0.3077 | 0.6667 | 0.9231 | 0.7124 | 4535.9 |
| Hybrid + Cross Encoder | 0.3077 | 0.6667 | 0.9231 | 0.7165 | 6104.3 |

## Highlights
- **Best Performing Category**: Negative Queries (100.00% pass rate)
- **Worst Performing Category**: Factual QA (0.00% pass rate)
- **Largest Failure Mode**: Unknown (8 occurrences)
- **Largest Retrieval Weakness**: Precision (Mean Precision: 0.2267, Mean Recall: 0.6889)
- **Largest Generation Weakness**: Faithfulness (Mean Faithfulness: 0.1333, Mean Relevancy: 0.7333)

## Failure Summary
- **Total Failures**: 13
  - Retrieval Failure: 1 (7.7%)
  - Unknown: 8 (61.5%)
  - Generation Hallucination: 4 (30.8%)