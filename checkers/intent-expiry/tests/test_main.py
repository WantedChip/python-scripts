import tempfile
import unittest
from pathlib import Path

from main import IntentAuditor


class TestIntentExpiry(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audit_todo_completed(self):
        code_file = self.repo_dir / "app.py"
        code_file.write_text(
            "# TODO: implement process_data\ndef process_data():\n    pass\n",
            encoding="utf-8",
        )

        auditor = IntentAuditor(self.repo_dir, use_git=False)
        items = auditor.audit()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].tag, "TODO")
        self.assertEqual(items[0].status, "COMPLETED")

    def test_audit_todo_active(self):
        code_file = self.repo_dir / "app.py"
        code_file.write_text(
            "# TODO: refactor database queries later\n",
            encoding="utf-8",
        )

        auditor = IntentAuditor(self.repo_dir, use_git=False)
        items = auditor.audit()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "ACTIVE")


if __name__ == "__main__":
    unittest.main()
