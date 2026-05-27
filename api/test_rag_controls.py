from unittest import TestCase
from unittest.mock import patch

import Milvus
from langchain_core.documents import Document
from rag.llm_orchestration import get_optimized_response


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
