from unittest import TestCase
from unittest.mock import patch

import Milvus


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
