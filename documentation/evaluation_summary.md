# AcademeRAG Evaluation Summary Report

## Overall Metrics
- **Total Cases**: 15
- **Overall Pass Rate**: 0.00%
- **Average Retrieval Latency**: 12111.7 ms
- **Average Generation Latency**: 26605.8 ms
- **Average Total Latency**: 82859.4 ms

## Per-Category Performance
| Category | Pass Rate | MRR | NDCG@5 | Faithfulness | Relevancy | Context Precision |
|---|---|---|---|---|---|---|
| Factual QA | 0.00% | 0.5000 | 1.4742 | 0.0000 | 0.5000 | 0.5000 |
| Syllabus QA | 0.00% | 0.0000 | 0.0000 | 0.0000 | 0.5000 | 0.0000 |
| Keyword Lookup | 0.00% | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |
| Summarization | 0.00% | 0.0000 | 0.0000 | 1.0000 | 0.5000 | 0.0000 |
| Negative Queries | 0.00% | 0.0000 | 0.5000 | 0.5000 | 0.0000 | 0.0000 |
| Multi-page Reasoning | 0.00% | 0.5000 | 1.4742 | 0.0000 | 1.0000 | 0.5000 |
| Table Extraction | 0.00% | 0.5000 | 1.4742 | 0.5000 | 1.0000 | 0.3750 |
| Semantic Retrieval | 0.00% | 0.0000 | 0.0000 | 0.0000 | 1.0000 | 0.0000 |

## Retrieval Ablation Benchmarks
| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Total Latency (ms) |
|---|---|---|---|---|---|
| Dense Only | 0.9538 | 2.4615 | 0.9615 | 1.7200 | 4130.0 |
| BM25 Only | 0.9231 | 2.1026 | 0.9231 | 1.4977 | 752.9 |
| Hybrid | 0.9231 | 2.3077 | 0.9231 | 1.6383 | 4449.6 |
| Hybrid + Cross Encoder | 0.2308 | 1.1538 | 0.2308 | 0.6804 | 9913.3 |

## Highlights
- **Best Performing Category**: Factual QA (0.00% pass rate)
- **Worst Performing Category**: Factual QA (0.00% pass rate)
- **Largest Failure Mode**: Retrieval Failure (10 occurrences)
- **Largest Retrieval Weakness**: Precision (Mean Precision: 0.2000, Mean Recall: 1.1333)
- **Largest Generation Weakness**: Faithfulness (Mean Faithfulness: 0.2667, Mean Relevancy: 0.6667)

## Failure Summary
- **Total Failures**: 15
  - Unknown: 1 (6.7%)
  - Retrieval Failure: 10 (66.7%)
  - Generation Hallucination: 4 (26.7%)