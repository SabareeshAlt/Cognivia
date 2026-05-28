# RAG Pipeline Scoring System Report

AcademeRAG-Final incorporates a robust, algorithmic RAG scoring pipeline to measure the accuracy, grounding, and reliability of retrieved information and generated answers.

---

## Evaluation Metrics

Every response evaluates five core metrics (each scored from 0 to 100):

### 1. Retrieval Relevance Score (40% Weight)
* **Objective**: Measure the structural relevance of the retrieved context.
* **Mechanism**: Computes the normalized average of:
  - **Cross-Encoder Reranker Score**: Normalizes logits using a sigmoid function:
    $$\text{Sigmoid}(x) = \frac{1}{1 + e^{-x}}$$
  - **RRF (Reciprocal Rank Fusion) Score**: Normalized against the theoretical maximum RRF score of 0.0333.
  - **Lexical Score**: BM25 relevance score normalized against a baseline of 15.0.

### 2. Context Coverage Score (25% Weight)
* **Objective**: Assess the lexical coverage of the user's query within the retrieved document chunks.
* **Mechanism**: Evaluates the term overlap ratio of key question words (excluding stopwords) against the combined retrieved chunks, multiplied by a retrieve-depth factor scaled by the number of documents.

### 3. Answer Grounding Score (25% Weight)
* **Objective**: Ensure that statements and technical terms generated in the answer are strictly supported by the context, preventing hallucinations.
* **Mechanism**: Evaluates what fraction of generated technical keywords, nouns, and numbers exist in the retrieved context.
  - **Refusal Handling**: If the LLM generates a refusal indicating that the context is insufficient (e.g., "not mentioned in the provided documents"), the grounding score is automatically set to **100.0** to reward correct abstention.

### 4. Citation Confidence Score (10% Weight)
* **Objective**: Validate that cited sources actually correspond to the retrieved documents.
* **Mechanism**: Extracts citations from the generated answer formatted as `[Source: File, Page: Number]` and checks what percentage of these matches the metadata of retrieved chunks.
  - **No Citation Penalty**: If assertions are made without citations, a citation score of **50.0** is applied.
  - **Refusal Exemption**: Refusals bypass citation checking and receive **100.0**.

---

## Final Weighted Score Calculation

The final pipeline score is computed as a weighted average:

$$\text{Final Score} = (\text{Retrieval} \times 0.40) + (\text{Context} \times 0.25) + (\text{Grounding} \times 0.25) + (\text{Citation} \times 0.10)$$

---

## Confidence Label Classification

Based on the final score, a confidence label is assigned:

| Score Range | Confidence Label |
| :--- | :--- |
| $\ge 95$ | Excellent |
| $\ge 85$ | High |
| $\ge 70$ | Moderate |
| $\ge 50$ | Low |
| $< 50$ | Weak |

---

## Frontend Integration

The final score and confidence label are streamed via Server-Sent Events (`type: "score"`) and displayed at the bottom of the assistant's message bubble:

- **Badge UI**: E.g. `RAG Score: 91/100 | Confidence: High`
- **Dynamic Color Indicators**: Green (Emerald) for Excellent/High, Orange (Amber) for Moderate, and Red (Rose) for Low/Weak.
- **Citation Chips**: Interactive source badges linking to cited documents and page numbers are appended below the answer card.
