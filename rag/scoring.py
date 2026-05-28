import math
import re
from typing import List
from langchain_core.documents import Document

# Copy tokenization helper and stopwords for self-containment
STOPWORDS = {
    "a", "an", "and", "are", "for", "from", "in", "is", "of", "on", "or", "the",
    "to", "what", "which", "with", "each", "tell", "me", "list", "show", "give",
    "according", "provided", "document", "documents", "source", "page", "based",
    "available", "program", "subject", "subjects", "course", "courses"
}

ANSWER_FRAMING_TERMS = {
    "according", "provided", "documents", "document", "based", "available", "source",
    "page", "following", "listed", "mentions", "include", "includes", "program",
    "b", "tech", "r", "pdf"
}

def _tokenize(text: str) -> List[str]:
    raw = text or ""
    # Extract compound technical terms (e.g. TCP/IP, Llama-3.3)
    compounds = re.findall(r'[A-Za-z][A-Za-z0-9]*(?:[+\-./][A-Za-z0-9]+)+', raw)
    compound_lower = [c.lower() for c in compounds]
    # Standard alphanumeric terms
    words = re.findall(r'[a-z0-9]+', raw.lower())
    return compound_lower + words

def calculate_retrieval_relevance_score(docs: List[Document], question: str = "") -> float:
    """
    Computes the normalized average of the Reranker, RRF, and Lexical scores 
    for the top retrieved context documents.
    """
    if not docs:
        return 0.0
        
    scores = []
    q_tokens = set(_tokenize(question)) - STOPWORDS
    # Evaluate top 3 documents
    for doc in docs[:3]:
        meta = doc.metadata or {}
        doc_scores = []
        
        # 1. Reranker Score (sigmoid normalization)
        if "rerank_score" in meta:
            r_score = float(meta["rerank_score"])
            # Sigmoid maps logit to [0, 1]
            sig = 1.0 / (1.0 + math.exp(-r_score))
            doc_scores.append(sig * 100.0)
            
        # 2. RRF Score (normalized against max RRF score of 0.0333)
        if "rrf_score" in meta:
            rrf = float(meta["rrf_score"])
            doc_scores.append(min(1.0, rrf / 0.0333) * 100.0)
            
        # 3. Lexical Score (BM25 score normalized)
        if "score" in meta:
            lex = float(meta["score"])
            doc_scores.append(min(1.0, lex / 15.0) * 100.0)
            
        if not doc_scores:
            doc_scores.append(70.0) # Baseline default for retrieved chunk

        if q_tokens:
            doc_tokens = set(_tokenize(doc.page_content))
            overlap_ratio = len(q_tokens & doc_tokens) / len(q_tokens)
            doc_scores.append(min(100.0, overlap_ratio * 140.0))

        if meta.get("source") and meta.get("page_number"):
            doc_scores.append(90.0)
            
        scores.append(sum(doc_scores) / len(doc_scores))
        
    return round(sum(scores) / len(scores), 1) if scores else 0.0

def calculate_context_coverage_score(question: str, docs: List[Document]) -> float:
    """
    Measures the term overlap ratio of key question words with the retrieved chunks.
    """
    if not docs:
        return 0.0
        
    q_tokens = set(_tokenize(question.lower())) - STOPWORDS
    if not q_tokens:
        return 100.0
        
    context_text = " ".join(doc.page_content.lower() for doc in docs)
    c_tokens = set(_tokenize(context_text))
    
    overlap = q_tokens & c_tokens
    ratio = len(overlap) / len(q_tokens)
    
    # Retrieve count multiplier (baseline coverage depth weight)
    count_factor = min(1.0, len(docs) / 3.0)
    score = ratio * 100.0 * (0.8 + 0.2 * count_factor)
    
    return round(min(100.0, max(0.0, score)), 1)

def calculate_answer_grounding_score(answer: str, docs: List[Document]) -> float:
    """
    Evaluates what fraction of generated technical keywords are grounded in the retrieved context.
    Correctly refusing to answer when context is missing receives a score of 100.
    """
    ans_lower = answer.lower()
    refusal_keywords = [
        "not found", "insufficient context", "do not have", "don't have",
        "cannot find", "no information", "not mentioned", "couldn't find"
    ]
    if any(k in ans_lower for k in refusal_keywords):
        return 100.0
        
    if not docs:
        return 0.0
        
    answer_without_citations = re.sub(r'\[Source:\s*[^\]]+\]', ' ', answer, flags=re.IGNORECASE)
    ans_words = _tokenize(answer_without_citations)
    ans_key_terms = set(
        w for w in ans_words 
        if w not in STOPWORDS and w not in ANSWER_FRAMING_TERMS and (w.isdigit() or len(w) >= 3)
    )
    
    if not ans_key_terms:
        return 100.0
        
    context_text = " ".join(doc.page_content.lower() for doc in docs)
    context_words = set(_tokenize(context_text))
    
    overlap = ans_key_terms & context_words
    grounding_ratio = len(overlap) / len(ans_key_terms)
    
    return round(min(100.0, max(0.0, grounding_ratio * 100.0)), 1)

def calculate_citation_confidence_score(answer: str, docs: List[Document]) -> float:
    """
    Evaluates whether output assertions trace back to retrieved sources.
    """
    ans_lower = answer.lower()
    refusal_keywords = [
        "not found", "insufficient context", "do not have", "don't have",
        "cannot find", "no information", "not mentioned", "couldn't find"
    ]
    if any(k in ans_lower for k in refusal_keywords):
        return 100.0
        
    if not docs:
        return 100.0
        
    citations = re.findall(r'\[Source:\s*([^,\]]+)(?:,\s*Page:?\s*\d+)?\]', answer, re.IGNORECASE)
    if not citations:
        return 50.0 # Penalty for claiming facts without references
        
    retrieved_sources = {doc.metadata.get("source", "").lower() for doc in docs if doc.metadata}
    
    matched = 0
    for cit in citations:
        cit_clean = cit.strip().lower()
        if any(cit_clean in src for src in retrieved_sources):
            matched += 1
            
    ratio = matched / len(citations)
    return round(ratio * 100.0, 1)

def get_confidence_label(score: float) -> str:
    if score >= 95:
        return "Excellent"
    elif score >= 85:
        return "High"
    elif score >= 70:
        return "Moderate"
    elif score >= 50:
        return "Low"
    else:
        return "Weak"

def compute_pipeline_score(question: str, answer: str, docs: List[Document]) -> dict:
    """
    Runs the final pipeline scoring calculation and confidence label assignment.
    """
    retrieval = calculate_retrieval_relevance_score(docs, question)
    context = calculate_context_coverage_score(question, docs)
    grounding = calculate_answer_grounding_score(answer, docs)
    citation = calculate_citation_confidence_score(answer, docs)
    
    final_score = (
        retrieval * 0.40 +
        context * 0.25 +
        grounding * 0.25 +
        citation * 0.10
    )
    final_score = round(final_score, 1)
    
    return {
        "retrieval_relevance_score": retrieval,
        "context_coverage_score": context,
        "answer_grounding_score": grounding,
        "citation_confidence_score": citation,
        "final_rag_score": final_score,
        "confidence_label": get_confidence_label(final_score)
    }
