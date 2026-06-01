from django.test import SimpleTestCase

from database import compute_sync_decision


class IndexSyncDecisionTests(SimpleTestCase):
    def test_forced_reindex_always_true(self):
        should_sync, reason = compute_sync_decision([], {}, force_reindex=True)
        self.assertTrue(should_sync)
        self.assertEqual(reason, "forced")

    def test_no_files_no_sync(self):
        should_sync, reason = compute_sync_decision([], {}, force_reindex=False)
        self.assertFalse(should_sync)
        self.assertEqual(reason, "no-documents")

    def test_unchanged_hashes_no_sync(self):
        files = [
            {"relative_path": "documents/a.pdf", "content_hash": "abc"},
            {"relative_path": "documents/b.pdf", "content_hash": "def"},
        ]
        tracked = {"documents/a.pdf": "abc", "documents/b.pdf": "def"}
        should_sync, reason = compute_sync_decision(files, tracked, force_reindex=False)
        self.assertFalse(should_sync)
        self.assertEqual(reason, "unchanged")

    def test_changed_hash_triggers_sync(self):
        files = [{"relative_path": "documents/a.pdf", "content_hash": "new"}]
        tracked = {"documents/a.pdf": "old"}
        should_sync, reason = compute_sync_decision(files, tracked, force_reindex=False)
        self.assertTrue(should_sync)
        self.assertIn("content-changed", reason)
