import os
import tempfile
import unittest
from agent import rag


class TestRagEmptyRunbooks(unittest.TestCase):
    def test_init_with_no_runbooks_dir(self):
        # Create a temporary working directory without a runbooks folder
        with tempfile.TemporaryDirectory() as tmpdir:
            cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                chroma_dir = os.path.join(tmpdir, "chroma_test_store")
                # Should not raise
                rag.init_rag_store(chroma_dir)
                # Retrieval should return empty string
                ctx = rag.get_runbook_context("test event")
                self.assertEqual(ctx, "")
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
