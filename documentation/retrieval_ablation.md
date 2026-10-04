# Cognivia Retrieval Ablation Study

| Retrieval Configuration | Precision@5 | Recall@5 | MRR | NDCG@5 | Avg Retrieval Latency (ms) | Avg Reranker Latency (ms) | Avg Total Latency (ms) |
|---|---|---|---|---|---|---|---|
| Dense Only | 0.2462 | 0.6154 | 0.9487 | 0.6530 | 4019.8 | 0.0 | 4019.9 |
| BM25 Only | 0.4000 | 0.6154 | 0.9231 | 0.6668 | 720.6 | 0.0 | 720.6 |
| Hybrid | 0.3077 | 0.6667 | 0.9231 | 0.7124 | 4535.8 | 0.0 | 4535.9 |
| Hybrid + Cross Encoder | 0.3077 | 0.6667 | 0.9231 | 0.7165 | 4227.1 | 1877.2 | 6104.3 |