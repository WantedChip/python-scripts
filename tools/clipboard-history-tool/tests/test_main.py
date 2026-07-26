"""Unit tests for Clipboard History Tool."""

import json
import os
import tempfile
import unittest

from main import ClipboardManager, SecretRedactor


class TestSecretRedactor(unittest.TestCase):
    """Test suite for secret detection and redaction."""

    def setUp(self) -> None:
        self.redactor = SecretRedactor()

    def test_redact_openai_key(self) -> None:
        raw = "My key is sk-1234567890abcdef1234567890abcdef"
        redacted = self.redactor.redact(raw)
        self.assertNotIn("sk-1234567890abcdef1234567890abcdef", redacted)
        self.assertIn("[REDACTED_OPENAI_KEY]", redacted)

    def test_redact_aws_key(self) -> None:
        raw = "AWS_KEY=AKIA1234567890ABCDEF"
        redacted = self.redactor.redact(raw)
        self.assertNotIn("AKIA1234567890ABCDEF", redacted)
        self.assertIn("[REDACTED_AWS_KEY]", redacted)

    def test_redact_password_pattern(self) -> None:
        raw = "password = mysecretpass123"
        redacted = self.redactor.redact(raw)
        self.assertIn("password: [REDACTED_SECRET]", redacted)

    def test_no_false_positives(self) -> None:
        raw = "Hello world this is a normal text."
        redacted = self.redactor.redact(raw)
        self.assertEqual(raw, redacted)


class TestClipboardManager(unittest.TestCase):
    """Test suite for ClipboardManager sqlite operations."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.mgr = ClipboardManager(db_path=self.temp_db.name)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def test_add_and_list_entries(self) -> None:
        entry_id = self.mgr.add_entry("Sample clipboard text")
        self.assertIsNotNone(entry_id)
        entries = self.mgr.list_entries(limit=10)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["content"], "Sample clipboard text")

    def test_deduplication(self) -> None:
        id1 = self.mgr.add_entry("Duplicate text")
        id2 = self.mgr.add_entry("Duplicate text")
        self.assertIsNotNone(id1)
        self.assertIsNone(id2)
        entries = self.mgr.list_entries()
        self.assertEqual(len(entries), 1)

    def test_search_entries(self) -> None:
        self.mgr.add_entry("Python programming code snippet", tags="code,py")
        self.mgr.add_entry("Shopping list: milk, bread")
        results = self.mgr.search_entries("programming")
        self.assertEqual(len(results), 1)
        self.assertIn("Python", results[0]["content"])

    def test_export_entries(self) -> None:
        self.mgr.add_entry("Exportable item")
        export_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        export_file.close()

        try:
            self.mgr.export_entries(export_file.name, format_type="json")
            with open(export_file.name, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["content"], "Exportable item")
        finally:
            if os.path.exists(export_file.name):
                os.unlink(export_file.name)

    def test_clear_history(self) -> None:
        self.mgr.add_entry("Item 1")
        self.mgr.add_entry("Item 2")
        self.mgr.clear_history()
        entries = self.mgr.list_entries()
        self.assertEqual(len(entries), 0)


if __name__ == "__main__":
    unittest.main()
