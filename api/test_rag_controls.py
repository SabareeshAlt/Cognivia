from unittest import TestCase
from unittest.mock import patch

import Milvus
from langchain_core.documents import Document


class RagControlsTests(TestCase):
    def test_dynamic_top_k_bounds(self):
        old_top_k = Milvus.TOP_K
        old_min = Milvus.DYNAMIC_TOP_K_MIN
        old_max = Milvus.DYNAMIC_TOP_K_MAX
        try:
            Milvus.TOP_K = 3
            Milvus.DYNAMIC_TOP_K_MIN = 2
            Milvus.DYNAMIC_TOP_K_MAX = 6
            self.assertEqual(Milvus._compute_dynamic_top_k("short question"), 3)
            self.assertEqual(Milvus._compute_dynamic_top_k("x" * 120), 4)
            self.assertEqual(Milvus._compute_dynamic_top_k("x" * 600), 5)
        finally:
            Milvus.TOP_K = old_top_k
            Milvus.DYNAMIC_TOP_K_MIN = old_min
            Milvus.DYNAMIC_TOP_K_MAX = old_max

    @patch("Milvus.compute_rebuild_state")
    @patch("Milvus._milvus_cloud_ready")
    def test_retrieval_diagnostics_shape(self, mock_ready, mock_rebuild_state):
        mock_rebuild_state.return_value = (False, "unchanged")
        mock_ready.return_value = True
        diag = Milvus.get_retrieval_diagnostics()
        self.assertIn("collection", diag)
        self.assertIn("chunk_profile", diag)
        self.assertIn("score_threshold", diag)
        self.assertEqual(diag["rebuild_reason"], "unchanged")

    def test_unit_title_query_requires_explicit_unit_headings(self):
        supported = [
            Document(
                page_content=(
                    "Unit I Foundations of Digital Logic\n"
                    "Unit II Combinational Logic Design\n"
                    "Unit III Sequential Logic Design"
                ),
                metadata={"page_number": 13},
            )
        ]
        unsupported = [
            Document(
                page_content=(
                    "Course Objectives: Provide comprehensive understanding of digital systems "
                    "and their fundamental components."
                ),
                metadata={"page_number": 1},
            )
        ]

        question = "What are the titles of each units in Digital Logic Design?"
        self.assertTrue(Milvus._has_explicit_support(question, supported))
        self.assertFalse(Milvus._has_explicit_support(question, unsupported))

    def test_fallback_retrieval_boosts_explicit_unit_heading_chunks(self):
        with patch(
            "Milvus._fallback_chunk_corpus",
            return_value=(
                Document(
                    page_content="Course Objectives: Learn digital systems, Boolean algebra, and PLDs.",
                    metadata={"page_number": 1},
                ),
                Document(
                    page_content=(
                        "Unit I Foundations of Digital Logic\n"
                        "Unit II Combinational Logic Design\n"
                        "Unit III Sequential Logic Design"
                    ),
                    metadata={"page_number": 13},
                ),
            ),
        ):
            docs = Milvus._fallback_retrieve_docs(
                "What are the titles of each units in Digital Logic Design?",
                1,
            )

        self.assertEqual(len(docs), 1)
        self.assertIn("Unit I Foundations of Digital Logic", docs[0].page_content)

    def test_assessment_unit_mentions_do_not_count_as_unit_titles(self):
        question = "What are the units provided in Digital Logic Design?"
        assessment_doc = Document(
            page_content=(
                "Assessment Methodology\n"
                "Written Test (Unit I & II)\n"
                "Written Test (Unit III & IV)"
            ),
            metadata={"page_number": 12},
        )
        syllabus_doc = Document(
            page_content=(
                "Unit I Foundations of Digital Logic\n"
                "Unit II Combinational Logic Design"
            ),
            metadata={"page_number": 13},
        )

        self.assertEqual(Milvus._explicit_unit_title_line_count(assessment_doc.page_content), 0)
        self.assertGreaterEqual(Milvus._explicit_unit_title_line_count(syllabus_doc.page_content), 2)
        self.assertGreater(
            Milvus._document_score(question, syllabus_doc)[0],
            Milvus._document_score(question, assessment_doc)[0],
        )

    def test_subject_phrase_boosts_matching_course(self):
        question = "What are the units provided in Digital Logic Design?"
        matching_doc = Document(
            page_content=(
                "DIGITAL LOGIC DESIGN\n"
                "Unit I Foundations of Digital Logic\n"
                "Unit II Combinational Logic Design"
            ),
            metadata={"page_number": 13},
        )
        non_matching_doc = Document(
            page_content=(
                "MACHINE LEARNING\n"
                "Unit I Introduction to Machine Learning\n"
                "Unit II Supervised Learning"
            ),
            metadata={"page_number": 96},
        )

        self.assertEqual(Milvus._query_subject_phrase(question), "digital logic design")
        self.assertGreater(
            Milvus._document_score(question, matching_doc)[0],
            Milvus._document_score(question, non_matching_doc)[0],
        )

    def test_syllabus_queries_include_adjacent_page(self):
        first_page = Document(
            page_content="DIGITAL LOGIC DESIGN\nUnit I Foundations of Digital Logic\nUnit II Combinational Logic Design",
            metadata={"document_path": "documents/RAG sample 2.pdf", "page_number": 13, "chunk_index": 0},
        )
        next_page = Document(
            page_content="Unit V Memories, Programmable Logic Devices\nMemory: Definition and types of ROM & RAM.",
            metadata={"document_path": "documents/RAG sample 2.pdf", "page_number": 14, "chunk_index": 0},
        )

        with patch("Milvus._fallback_chunk_corpus", return_value=(first_page, next_page)):
            augmented = Milvus._augment_docs_for_syllabus(
                "What are the syllabus of Digital Logic Design?",
                [first_page],
            )

        self.assertEqual(len(augmented), 2)
        self.assertIn("Unit V Memories, Programmable Logic Devices", augmented[1].page_content)

    def test_answer_generation_runs_when_docs_exist(self):
        docs = [Document(page_content="Course Objectives: Learn Boolean algebra.", metadata={"page_number": 10})]
        with patch("Milvus._retrieve_docs", return_value=docs), patch(
            "Milvus._augment_docs_for_syllabus",
            return_value=docs,
        ), patch("Milvus._invoke_with_provider_failover", return_value="Grounded answer") as mock_invoke:
            answer = Milvus.get_optimized_response("What are the course objectives of Digital Logic Design?")

        self.assertEqual(answer, "Grounded answer")
        mock_invoke.assert_called_once()
