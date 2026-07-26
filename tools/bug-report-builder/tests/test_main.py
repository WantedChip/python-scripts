"""Unit tests for bug-report-builder main.py."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import (
    BugReport,
    compile_json_report,
    compile_markdown_report,
    get_sanitized_env_vars,
    get_system_environment,
    main,
    read_attachment,
    run_command,
    sanitize_text,
)


class TestBugReportBuilder(unittest.TestCase):
    """Test suite for Bug Report Builder functions."""

    def test_sanitize_text_secrets(self) -> None:
        """Test redacting secrets, JWTs, AWS keys, and bearer tokens."""
        raw_text = (
            "Error with Bearer abcdef123456789 and AKIA1234567890ABCDEF\n"
            "api_key=secret_value_123; token='mytoken123'"
        )
        sanitized = sanitize_text(raw_text)
        self.assertNotIn("Bearer abcdef123456789", sanitized)
        self.assertNotIn("AKIA1234567890ABCDEF", sanitized)
        self.assertNotIn("secret_value_123", sanitized)

    def test_get_sanitized_env_vars(self) -> None:
        """Test redacting environment variables matching secret keywords."""
        env_dict = {"SECRET_TOKEN": "super_secret", "PUBLIC_VAR": "hello"}
        with patch.dict(os.environ, env_dict):
            env_vars = get_sanitized_env_vars()
            self.assertEqual(env_vars.get("SECRET_TOKEN"), "[REDACTED]")
            self.assertEqual(env_vars.get("PUBLIC_VAR"), "hello")

    def test_get_system_environment(self) -> None:
        """Test retrieving system environment metadata."""
        env = get_system_environment()
        self.assertIn("os", env)
        self.assertIn("python_version", env)

    def test_run_command(self) -> None:
        """Test executing a simple echo command."""
        cmd = "python -c \"print('hello stdout')\""
        ret_code, stdout, stderr, duration = run_command(cmd)
        self.assertEqual(ret_code, 0)
        self.assertIn("hello stdout", stdout)
        self.assertGreaterEqual(duration, 0)

    def test_read_attachment(self) -> None:
        """Test reading and sanitizing an attachment file."""
        with tempfile.NamedTemporaryFile("w+", delete=False, encoding="utf-8") as tmp:
            tmp.write("AWS Key: AKIA1234567890ABCDEF")
            tmp_path = tmp.name

        try:
            att = read_attachment(tmp_path)
            self.assertNotIn("AKIA1234567890ABCDEF", att["content"])
            self.assertIn("[REDACTED]", att["content"])
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_report_compilation(self) -> None:
        """Test Markdown and JSON report rendering."""
        report = BugReport(
            title="Test Issue",
            timestamp="2026-07-24 12:00:00 UTC",
            environment={"os": "Windows"},
            sanitized_env_vars={"PATH": "/bin"},
            command="python fail.py",
            return_code=1,
            duration_seconds=0.123,
            stdout="Starting...",
            stderr="Traceback failure",
            log_content=None,
            expected_behavior="Should exit 0",
            actual_behavior="Exited 1",
            attachments=[],
        )

        md = compile_markdown_report(report)
        self.assertIn("# Bug Report: Test Issue", md)
        self.assertIn("Traceback failure", md)

        js = compile_json_report(report)
        data = json.loads(js)
        self.assertEqual(data["title"], "Test Issue")
        self.assertEqual(data["return_code"], 1)

    def test_main_cli_execution(self) -> None:
        """Test main CLI function with temporary output file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output_report.md"
            ret = main(
                [
                    "--command",
                    "python -c \"import sys; sys.stderr.write('err'); sys.exit(2)\"",
                    "--output",
                    str(out_file),
                    "--title",
                    "CLI Test Report",
                ]
            )
            self.assertEqual(ret, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("CLI Test Report", content)


if __name__ == "__main__":
    unittest.main()
