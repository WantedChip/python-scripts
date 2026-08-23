"""Unit tests for Clipboard History Tool."""

import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from typing import Any, List

from main import ClipboardManager, SecretRedactor, main


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

    def test_redact_bearer_token(self) -> None:
        raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.token"
        redacted = self.redactor.redact(raw)
        self.assertIn("Bearer [REDACTED_TOKEN]", redacted)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", redacted)

    def test_redact_github_token(self) -> None:
        token = "ghp_" + "abcdef" * 6  # exactly 36 alnum chars after prefix
        redacted = self.redactor.redact(f"value {token}")
        self.assertIn("[REDACTED_GITHUB_TOKEN]", redacted)
        self.assertNotIn(token, redacted)

    def test_redact_private_key_block(self) -> None:
        raw = (
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK\nabc\n"
            "-----END RSA PRIVATE KEY-----"
        )
        redacted = self.redactor.redact(raw)
        self.assertIn("[REDACTED_PRIVATE_KEY]", redacted)
        self.assertNotIn("MIIEpAIBAAK", redacted)

    def test_custom_patterns_override_defaults(self) -> None:
        custom = SecretRedactor(patterns=[(r"foo-\d+", "[X]")])
        self.assertEqual(custom.redact("id foo-42 done"), "id [X] done")


class TestClipboardManager(unittest.TestCase):
    """Test suite for ClipboardManager sqlite operations."""

    def setUp(self) -> None:
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.mgr = ClipboardManager(db_path=self.temp_db.name)

    def tearDown(self) -> None:
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)

    def _fetch_preview(self, entry_id: int) -> Any:
        """Reads ``raw_content_preview`` straight from the database."""
        conn = sqlite3.connect(self.mgr.db_path)
        try:
            row = conn.execute(
                "SELECT raw_content_preview FROM clipboard_history WHERE id=?",
                (entry_id,),
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

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

    def test_whitespace_only_text_is_rejected(self) -> None:
        self.assertIsNone(self.mgr.add_entry("   \n\t"))

    def test_deduplication_only_against_latest_entry(self) -> None:
        first = self.mgr.add_entry("alpha")
        second = self.mgr.add_entry("beta")
        third = self.mgr.add_entry("alpha")
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNotNone(third)
        self.assertEqual(len(self.mgr.list_entries()), 3)

    def test_redaction_applied_by_default_and_skipped_on_request(self) -> None:
        secret = "password=hunter2secret"
        redacted_id = self.mgr.add_entry(secret)
        stored = self.mgr.list_entries()[0]["content"]
        self.assertIn("[REDACTED_SECRET]", stored)
        self.assertNotIn("hunter2secret", stored)

        self.mgr.add_entry(secret, redact=False)
        contents = [e["content"] for e in self.mgr.list_entries()]
        self.assertIn(secret, contents)
        self.assertIsNotNone(redacted_id)

    def test_long_content_preview_is_truncated_with_ellipsis(self) -> None:
        long_text = "x" * 50
        entry_id = self.mgr.add_entry(long_text)
        preview = self._fetch_preview(entry_id)
        self.assertTrue(preview.startswith("x" * 30))
        self.assertTrue(preview.endswith("..."))
        self.assertEqual(len(preview), 33)

    def test_short_content_preview_has_no_ellipsis(self) -> None:
        entry_id = self.mgr.add_entry("short")
        preview = self._fetch_preview(entry_id)
        self.assertEqual(preview, "short")

    def test_txt_export_writes_headers_and_separators(self) -> None:
        self.mgr.add_entry("plain note", tags="notes")
        export_path = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        export_path.close()
        try:
            result = self.mgr.export_entries(export_path.name, format_type="txt")
            self.assertEqual(result, export_path.name)
            body = open(export_path.name, encoding="utf-8").read()
            self.assertIn("(ID:", body)
            self.assertIn("plain note", body)
            self.assertIn("-" * 40, body)
        finally:
            if os.path.exists(export_path.name):
                os.unlink(export_path.name)


def _run_cli(args: List[str]) -> Any:
    """Runs ``main`` capturing stdout; returns (exit_code, output)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = main(args)
    return exit_code, buffer.getvalue()


class TestCliEntrypoint(unittest.TestCase):
    """End-to-end CLI runs against a temporary working directory."""

    def setUp(self) -> None:
        self.prev_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_dir_name = self.temp_dir.name
        os.chdir(self.temp_dir_name)
        # addCleanup runs LIFO: restore cwd first, delete dir afterwards.
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(os.chdir, self.prev_cwd)

    def test_add_list_and_clear_flow(self) -> None:
        code, out = _run_cli(["add", "first note"])
        self.assertEqual(code, 0)
        self.assertIn("Added clipboard entry ID: 1", out)

        _, out = _run_cli(["add", "first note"])
        self.assertIn("Duplicate or empty entry skipped.", out)

        code, out = _run_cli(["list", "--limit", "5"])
        self.assertEqual(code, 0)
        self.assertIn("[1]", out)
        self.assertIn("first note", out)

        _, out = _run_cli(["clear"])
        self.assertIn("Clipboard history cleared.", out)
        _, out = _run_cli(["list"])
        self.assertEqual(out.strip(), "")

    def test_add_without_flag_redacts_secrets(self) -> None:
        code, out = _run_cli(["add", "api_key=supersecret123", "--tags", "creds"])
        self.assertEqual(code, 0)
        _, out = _run_cli(["list"])
        self.assertIn("api_key: [REDACTED_SECRET]", out)
        self.assertNotIn("supersecret123", out)

    def test_add_no_redact_keeps_raw_secret_in_db(self) -> None:
        _run_cli(["add", "token=rawvalue999", "--no-redact"])
        _, out = _run_cli(["list"])
        self.assertIn("token=rawvalue999", out)

    def test_search_reports_match_count(self) -> None:
        _run_cli(["add", "unique needle text here"])
        _run_cli(["add", "unrelated entry"])
        code, out = _run_cli(["search", "--query", "needle"])
        self.assertEqual(code, 0)
        self.assertIn("Found 1 matching entries:", out)
        self.assertIn("needle", out)

    def test_export_json_and_prints_destination(self) -> None:
        _run_cli(["add", "export me"])
        target = os.path.join(self.temp_dir.name, "dump.json")
        code, out = _run_cli(["export", "--output", target])
        self.assertEqual(code, 0)
        self.assertIn(f"Exported history to {target}", out)
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[0]["content"], "export me")

    def test_export_txt_format_option(self) -> None:
        _run_cli(["add", "text mode item"])
        target = os.path.join(self.temp_dir.name, "dump.txt")
        code, out = _run_cli(["export", "--output", target, "--format", "txt"])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(target))

    def test_empty_clipboard_search_reports_zero_matches(self) -> None:
        _, out = _run_cli(["search", "--query", "anything"])
        self.assertIn("Found 0 matching entries:", out)


if __name__ == "__main__":
    unittest.main()
