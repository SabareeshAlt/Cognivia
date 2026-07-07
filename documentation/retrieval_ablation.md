# AcademeRAG Retrieval Ablation Study

| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Avg Retrieval Latency (ms) | Avg Reranker Latency (ms) | Avg Total Latency (ms) |
|---|---|---|---|---|---|---|---|
| Dense Only | 0.9538 | 2.4615 | 0.9615 | 1.7200 | 4130.0 | 0.0 | 4130.0 |
| BM25 Only | 0.9231 | 2.1026 | 0.9231 | 1.4977 | 752.9 | 0.0 | 752.9 |
| Hybrid | 0.9231 | 2.3077 | 0.9231 | 1.6383 | 4449.6 | 0.0 | 4449.6 |
| Hybrid + Cross Encoder | 0.2308 | 1.1538 | 0.2308 | 0.6804 | 4434.2 | 5479.1 | 9913.3 |