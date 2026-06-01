"""
database/metadata.py
--------------------
Source filtering, citation metadata, syllabus query classification,
document scoring, and syllabus text cleaning utilities.
"""

import logging
import re
from collections import Counter
from functools import lru_cache
from typing import List, Optional

from langchain_core.documents import Document

from database.config import STOPWORDS, _SYLLABUS_NOISE_HEADINGS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source detection
# ---------------------------------------------------------------------------

def _available_sources() -> set[str]:
    """Return the set of PDF source names currently on disk."""
    from database.ingestion import get_pdf_files
    import os
    return {os.path.basename(path) for path in get_pdf_files()}


def _extract_target_sources(question: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", (question or "").strip().lower())
    if not normalized:
        return set()

    available_sources = sorted(_available_sources())
    if not available_sources:
        return set()

    by_lower = {source.lower(): source for source in available_sources}
    targets: set[str] = set()

    for source_lower, source in by_lower.items():
        if source_lower in normalized:
            targets.add(source)

    ordinal_to_number = {
        "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    }
    number_candidates: set[int] = set()

    for match in re.findall(r"\brag\s*sample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bsample\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\bpdf\s*(\d{1,2})\b", normalized):
        number_candidates.add(int(match))
    for match in re.findall(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:pdf|document|sample)\b", normalized):
        number_candidates.add(int(match))

    for word, number in ordinal_to_number.items():
        if re.search(rf"\b{word}\s+(?:pdf|document|sample)\b", normalized):
            number_candidates.add(number)

    for number in number_candidates:
        candidate = f"RAG sample {number}.pdf".lower()
        source = by_lower.get(candidate)
        if source:
            targets.add(source)

    return targets


def _milvus_escape_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _milvus_source_filter_expr(target_sources: set[str]) -> Optional[str]:
    if not target_sources:
        return None
    ordered = sorted(target_sources)
    if len(ordered) == 1:
        return f'source == "{_milvus_escape_literal(ordered[0])}"'
    joined = ", ".join(f'"{_milvus_escape_literal(source)}"' for source in ordered)
    return f"source in [{joined}]"


def _doc_source(doc: Document) -> str:
    return str((doc.metadata or {}).get("source") or "")


def _filter_docs_by_sources(docs: list[Document], target_sources: set[str]) -> list[Document]:
    if not target_sources:
        return docs
    allowed = {source.lower() for source in target_sources}
    return [doc for doc in docs if _doc_source(doc).lower() in allowed]


# ---------------------------------------------------------------------------
# Tokenizer (shared with BM25)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Tokenize text preserving compound technical terms like C++, TCP/IP, Node.js, Llama-3.3."""
    raw = text or ""
    compounds = re.findall(r'[A-Za-z][A-Za-z0-9]*(?:[+\-./ ][A-Za-z0-9]+)+', raw)
    compound_lower = [c.lower().replace(" ", "-") for c in compounds]
    words = re.findall(r'[a-z0-9]+', raw.lower())
    return compound_lower + words


# ---------------------------------------------------------------------------
# Query analysis
# ---------------------------------------------------------------------------

def _query_keywords(question: str) -> set[str]:
    return {token for token in _tokenize(question) if token not in STOPWORDS}


def _query_subject_phrases(question: str) -> list[str]:
    raw = (question or '').strip()
    if not raw:
        return []
    normalized = re.sub(r'\s+', ' ', raw.lower().rstrip('?.!'))
    candidates: list[str] = []
    if 'following subjects' in normalized:
        tail = re.split(
            r'following subjects(?:\s+in\s+[a-z0-9 &/-]+)?\s*[:\-]?',
            raw, flags=re.IGNORECASE, maxsplit=1
        )
        subject_block = tail[1] if len(tail) > 1 else raw
        subject_block = re.sub(r'\s{2,}', '\n', subject_block)
        for line in subject_block.splitlines():
            phrase = re.sub(r'^[\-\*\•\d\.\)\(]+\s*', '', line).strip(' ,;:-')
            if len(phrase) >= 4:
                candidates.append(phrase.lower())
    else:
        matches = list(re.finditer(r'\b(?:in|of|for)\s+([a-z][a-z0-9 &/-]{4,})$', normalized))
        if matches:
            phrase = matches[-1].group(1).strip()
            if ' in ' in phrase:
                phrase = phrase.rsplit(' in ', 1)[-1].strip()
            candidates.append(phrase)
    cleaned: list[str] = []
    seen: set[str] = set()
    for phrase in candidates:
        phrase = re.sub(r'\s+', ' ', phrase.strip())
        for prefix in ('course ', 'subject ', 'the course ', 'the subject '):
            if phrase.startswith(prefix):
                phrase = phrase[len(prefix):].strip()
        if len(phrase) < 4:
            continue
        if phrase in {'easwari engineering college', 'the following subjects'}:
            continue
        if phrase not in seen:
            seen.add(phrase)
            cleaned.append(phrase)
    return cleaned


def _query_subject_phrase(question: str) -> Optional[str]:
    phrases = _query_subject_phrases(question)
    if len(phrases) != 1:
        return None
    return phrases[0]


def _is_multi_subject_query(question: str) -> bool:
    return len(_query_subject_phrases(question)) >= 2


def _is_unit_title_query(question: str) -> bool:
    normalized = (question or '').lower()
    return 'unit' in normalized and (
        'title' in normalized or 'titles' in normalized
        or 'name' in normalized or 'names' in normalized
    )


def _is_syllabus_query(question: str) -> bool:
    normalized = (question or '').lower()
    return 'syllabus' in normalized or 'unit' in normalized or 'units' in normalized


def _unit_heading_count(text: str) -> int:
    return len(re.findall(r'\bunit\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\b', (text or '').lower()))


def _explicit_unit_title_line_count(text: str) -> int:
    return len(re.findall(
        r'(?im)^\s*unit\s+(?:i|ii|iii|iv|v|vi|vii|viii|ix|x|\d+)\s+[a-z][a-z0-9 ,&()/:-]{3,}$',
        (text or '').lower()
    ))


# ---------------------------------------------------------------------------
# Document scoring
# ---------------------------------------------------------------------------

def _document_score(question: str, doc: Document) -> tuple[int, int, int]:
    text = doc.page_content or ''
    normalized = text.lower()
    subject_phrases = _query_subject_phrases(question)
    multi_subject = len(subject_phrases) >= 2
    subject_phrase = subject_phrases[0] if len(subject_phrases) == 1 else None
    tokens = Counter(_tokenize(text))
    keyword_score = sum(
        min(freq, tokens[token])
        for token, freq in Counter(_query_keywords(question)).items()
    )
    boost = 0
    if _is_syllabus_query(question):
        unit_count = _unit_heading_count(text)
        explicit_unit_titles = _explicit_unit_title_line_count(text)
        if explicit_unit_titles:
            boost += explicit_unit_titles * 10
        elif unit_count:
            boost += unit_count
        if 'digital logic design' in normalized:
            boost += 4
        if 'course objectives' in normalized:
            boost -= 4
        if 'program outcomes' in normalized:
            boost -= 4
        if 'assessment methodology' in normalized or 'written test' in normalized:
            boost -= 5
        if subject_phrases:
            matches = sum(1 for phrase in subject_phrases if phrase in normalized)
            if matches:
                boost += 8 * matches
            elif subject_phrase:
                boost -= 20
            elif multi_subject:
                boost -= 1
    page_number = int((doc.metadata or {}).get('page_number') or 0)
    return (keyword_score + boost, boost, -page_number)


def _has_explicit_support(question: str, docs: list[Document]) -> bool:
    if not docs:
        return False
    if _is_syllabus_query(question):
        return any(_explicit_unit_title_line_count(doc.page_content) >= 1 for doc in docs)
    keywords = _query_keywords(question)
    if not keywords:
        return False
    for doc in docs:
        doc_tokens = set(_tokenize(doc.page_content))
        overlap = len(keywords & doc_tokens)
        if overlap >= max(2, min(4, len(keywords))):
            return True
    return False


def _generic_retrieval_boost(question: str, doc: Document) -> float:
    text = doc.page_content or ''
    normalized = text.lower()
    subject_phrases = _query_subject_phrases(question)
    subject_phrase = subject_phrases[0] if len(subject_phrases) == 1 else None
    boost = 0.0
    if len(subject_phrases) >= 2:
        phrase_matches = sum(1 for phrase in subject_phrases if phrase in normalized)
        if phrase_matches:
            boost += 1.5 * phrase_matches
    elif subject_phrase:
        if subject_phrase in normalized:
            boost += 3.5
        else:
            boost -= 1.5
    query_text = (question or '').lower()
    if 'lab' in query_text and 'practical' in normalized:
        boost += 1.0
    if 'objective' in query_text and 'course objectives' in normalized:
        boost += 2.0
    if 'experiment' in query_text and ('ex no' in normalized or 'experiment' in normalized):
        boost += 2.0
    if 'syllabus' in query_text and 'total periods' in normalized:
        boost += 0.5
    return boost


# ---------------------------------------------------------------------------
# Syllabus text cleaning
# ---------------------------------------------------------------------------

def _is_syllabus_noise_heading(line: str) -> bool:
    normalized = re.sub(r'\s+', ' ', (line or '').strip().lower()).rstrip(':')
    if not normalized:
        return False
    return any(normalized.startswith(prefix) for prefix in _SYLLABUS_NOISE_HEADINGS)


def _is_page_header_line(line: str) -> bool:
    normalized = re.sub(r'\s+', ' ', (line or '').strip().lower())
    return bool(normalized and (
        normalized.startswith('directorate of technical education')
        or normalized.startswith('2023 regulation')
        or normalized == 'theory 3 0 0 3'
        or (normalized == 'practicum 1 0 4 3')
        or (normalized == 'practical 0 0 4 2')
        or re.fullmatch(r'\d+', normalized)
    ))


def _is_syllabus_noise_item(line: str) -> bool:
    stripped = (line or '').strip()
    normalized = stripped.lower()
    if not stripped:
        return True
    if _is_page_header_line(stripped):
        return True
    if re.match(r'^(?:https?://|www\.)', normalized):
        return True
    if re.match(r'^[\d]+\s*[\.]\)\s+', stripped):
        return True
    if re.match(r'^[•\-]\s*', stripped):
        return True
    if normalized.startswith(('hardware requirement', 'software requirement', 'the following student')):
        return True
    bibliography_markers = (
        'edition', 'press', 'pearson', 'mc-graw', 'mcgraw', 'wiley', 'springer',
        'oxford', 'universities press', 'university press', "o'reilly", 'oreilly',
        'publication', 'publications', 'education services', 'pvt. ltd',
    )
    if any(marker in normalized for marker in bibliography_markers):
        return True
    if re.search(r'\b(19|20)\d{2}\b', normalized):
        return True
    return False


def _clean_syllabus_text(text: str) -> str:
    lines = [line.rstrip() for line in (text or '').splitlines()]
    cleaned: list[str] = []
    skipping_noise = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if cleaned and cleaned[-1] != '':
                cleaned.append('')
            continue
        if _is_page_header_line(line):
            continue
        if _is_syllabus_noise_heading(line):
            skipping_noise = True
            continue
        if skipping_noise:
            if re.match(r'(?i)^unit\s+[ivxlcdm]+\b', line) or re.match(r'(?i)^total\s+(?:hours|periods)\b', line):
                skipping_noise = False
            elif _is_syllabus_noise_heading(line) or _is_syllabus_noise_item(line):
                continue
            else:
                skipping_noise = False
        if cleaned and cleaned[-1] == '' and (line == ''):
            continue
        cleaned.append(line)
    compacted = '\n'.join(cleaned)
    compacted = re.sub(r'\n{3,}', '\n\n', compacted)
    return compacted.strip()


# ---------------------------------------------------------------------------
# Syllabus augmentation
# ---------------------------------------------------------------------------

def _augment_docs_for_syllabus(question: str, docs: list[Document]) -> list[Document]:
    if not _is_syllabus_query(question) or not docs:
        return docs
    from database.bm25 import _fallback_chunk_corpus
    corpus = _fallback_chunk_corpus()
    by_page: dict[tuple, Document] = {}
    for doc in corpus:
        key = (
            (doc.metadata or {}).get('document_path'),
            (doc.metadata or {}).get('page_number'),
        )
        existing = by_page.get(key)
        if existing is None:
            by_page[key] = doc
            continue
        current_index = int((doc.metadata or {}).get('chunk_index') or 0)
        existing_index = int((existing.metadata or {}).get('chunk_index') or 0)
        if current_index < existing_index:
            by_page[key] = doc
    augmented = list(docs)
    seen = {
        (
            (doc.metadata or {}).get('document_path'),
            (doc.metadata or {}).get('page_number'),
            (doc.metadata or {}).get('chunk_index'),
        )
        for doc in docs
    }
    for doc in docs:
        page_number = (doc.metadata or {}).get('page_number')
        document_path = (doc.metadata or {}).get('document_path')
        if not document_path or not isinstance(page_number, int):
            continue
        if _explicit_unit_title_line_count(doc.page_content) < 1:
            continue
        next_doc = by_page.get((document_path, page_number + 1))
        if not next_doc:
            continue
        next_key = (
            (next_doc.metadata or {}).get('document_path'),
            (next_doc.metadata or {}).get('page_number'),
            (next_doc.metadata or {}).get('chunk_index'),
        )
        if next_key not in seen:
            augmented.append(next_doc)
            seen.add(next_key)
    return augmented
