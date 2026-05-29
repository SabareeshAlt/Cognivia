from unittest import TestCase
from unittest.mock import patch

import Milvus
from langchain_core.documents import Document
from rag.llm_orchestration import get_optimized_response
from rag.scoring import compute_pipeline_score


class RagControlsTests(TestCase):
    def test_answer_generation_runs_when_docs_exist(self):
        docs = [Document(page_content="Course Objectives: Learn Boolean algebra.", metadata={"page_number": 10})]
        with patch("Milvus._retrieve_docs", return_value=docs), patch(
            "Milvus._augment_docs_for_syllabus",
            return_value=docs,
        ), patch("rag.llm_orchestration._invoke_with_provider_failover", return_value="Grounded answer") as mock_invoke:
            answer = get_optimized_response("What are the course objectives of Digital Logic Design?")

        self.assertEqual(answer, "Grounded answer")
        mock_invoke.assert_called_once()

    def test_scoring_accepts_page_citations_and_grounded_catalog_answers(self):
        docs = [
            Document(
                page_content=(
                    "Semester IV Information Technology Professional Elective I "
                    "Professional Elective II Professional Elective III "
                    "Employability Enhancement Course Mandatory Course"
                ),
                metadata={
                    "source": "RAG sample 3.pdf",
                    "page_number": 68,
                    "score": 18.0,
                    "rrf_score": 0.0333,
                    "rerank_score": 4.0,
                },
            )
        ]
        answer = (
            "Professional Elective I, Professional Elective II, Professional Elective III, "
            "Employability Enhancement Course, and Mandatory Course "
            "[Source: RAG sample 3.pdf, Page 68]"
        )

        score = compute_pipeline_score("List the semester IV subjects", answer, docs)

        self.assertGreaterEqual(score["final_rag_score"], 90.0)
        self.assertIn(score["confidence_label"], ["High", "Excellent"])
        self.assertEqual(score["citation_confidence_score"], 100.0)

